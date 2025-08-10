import argparse
import asyncio
import logging
import signal
import sys
import time
from typing import Any, Protocol

from switchbot import GetSwitchbotDevices

from .config import AppSettings
from .config_loader import load_settings_from_cli
from .error import ConfigError
from .exporter import PrometheusExporter
from .handlers import AutomationHandler
from .logging import setup_logging
from .mqtt import MqttClient
from .scanner import SwitchbotClient
from .signals import publish_mqtt_message_request
from .store import StateStore

logger = logging.getLogger(__name__)


class Component(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class Application:
    def __init__(self, settings: AppSettings, cli_args: argparse.Namespace):
        self.settings = settings
        self.cli_args = cli_args
        self.stopping = False
        self.is_reloading = False

        setup_logging(self.settings)

        self.storage = StateStore()
        self._components: dict[str, Component] = self._create_all_components(
            self.settings
        )
        publish_mqtt_message_request.connect(self._handle_publish_request)

    def _handle_publish_request(self, sender: Any, **kwargs) -> None:
        asyncio.create_task(self._handle_publish_request_async(sender, **kwargs))

    async def _handle_publish_request_async(self, sender: Any, **kwargs) -> None:
        timeout_seconds = 5.0
        start_time = time.time()

        while self.is_reloading:
            if time.time() - start_time > timeout_seconds:
                logger.error(
                    f"Failed to publish MQTT message: "
                    f"reload process timed out after {timeout_seconds}s."
                )
                return
            await asyncio.sleep(0.1)

        mqtt_client = self._components.get("mqtt")
        if isinstance(mqtt_client, MqttClient):
            await mqtt_client.publish(**kwargs)
        else:
            logger.warning("MQTT component is not configured, cannot publish message.")

    def _create_all_components(self, settings: AppSettings) -> dict[str, Component]:
        components: dict[str, Component] = {}

        ble_scanner = GetSwitchbotDevices(interface=settings.scanner.interface)
        components["scanner"] = SwitchbotClient(
            scanner=ble_scanner,
            store=self.storage,
            cycle=settings.scanner.cycle,
            duration=settings.scanner.duration,
        )

        if settings.mqtt:
            components["mqtt"] = MqttClient(settings.mqtt)

        if settings.prometheus_exporter.enabled:
            components["prometheus_exporter"] = PrometheusExporter(
                settings=settings.prometheus_exporter
            )

        if settings.automations:
            components["automations"] = AutomationHandler(
                configs=settings.automations, state_store=self.storage
            )

        return components

    async def reload_settings(self):
        if self.is_reloading:
            logger.warning("Reload already in progress, ignoring request.")
            return

        logger.info("SIGHUP received, reloading configuration.")
        self.is_reloading = True
        old_components = self._components
        old_settings = self.settings

        try:
            new_settings = load_settings_from_cli(self.cli_args)
            setup_logging(new_settings)
            new_components = self._create_all_components(new_settings)

            logger.info("Stopping old components...")
            await self._stop_components(old_components)

            self.settings = new_settings
            self._components = new_components

            logger.info("Starting new components...")
            await self._start_components(self._components)

            logger.info("Configuration reloaded and components restarted successfully.")

        except ConfigError as e:
            logger.error(
                f"Failed to load new configuration, keeping the old. Reason:\n{e}"
            )
            # Rollback: If new settings couldn't be loaded, just log and return.
            # No components were stopped or started yet.
            self._components = old_components  # Ensure components reference is correct
            self.settings = old_settings  # Ensure settings reference is correct
            logger.info("No changes applied due to configuration error.")
        except Exception as e:
            logger.error(f"Failed to apply new configuration: {e}", exc_info=True)
            logger.info("Rolling back to the previous configuration.")
            self.settings = old_settings  # Rollback to old settings
            self._components = old_components  # Rollback to old components

            try:
                logger.info("Restarting old components...")
                await self._start_components(self._components)
                logger.info("Rollback successful.")
            except Exception as rollback_e:
                logger.critical(f"Rollback failed: {rollback_e}", exc_info=True)
                logger.debug("Exiting due to rollback failure.", exc_info=True)
                sys.exit(1)
        finally:
            self.is_reloading = False

    async def _start_components(self, components: dict[str, Component]) -> None:
        logger.info("Starting components...")
        await asyncio.gather(*[c.start() for c in components.values()])
        logger.info("Components started successfully.")

    async def _stop_components(self, components: dict[str, Component]) -> None:
        logger.info("Stopping components...")
        # Stop components in reverse order of creation for graceful shutdown
        for key in reversed(list(components.keys())):
            component = components[key]
            await component.stop()
        logger.info("Components stopped successfully.")

    async def start(self):
        logger.info("Starting all components...")
        await self._start_components(self._components)

    async def stop(self):
        if self.stopping:
            return
        self.stopping = True

        logger.info("Stopping all components...")
        await self._stop_components(self._components)


async def run_app(settings: AppSettings, args: argparse.Namespace):
    app = None
    shutdown_event = asyncio.Event()

    def graceful_shutdown():
        if not shutdown_event.is_set():
            logger.info("Shutdown signal received. Initiating graceful shutdown...")
            shutdown_event.set()

    try:
        app = Application(settings, args)
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, graceful_shutdown)

        loop.add_signal_handler(
            signal.SIGHUP, lambda: asyncio.create_task(app.reload_settings())
        )

        await app.start()
        logger.info("Application started successfully. Waiting for signals...")

        await shutdown_event.wait()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except OSError as e:
        logger.critical(
            f"Application encountered a critical error during startup and will exit: "
            f"{e}",
            exc_info=True,
        )
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        if "app" in locals() and app:
            await app.stop()
