import argparse
import asyncio
import logging
import signal
import sys
import time
from typing import Any, Dict, Union, cast

from .component import BaseComponent
from .config import AppSettings
from .config_loader import load_settings_from_cli
from .handlers import AutomationHandler
from .logging import setup_logging
from .mqtt import MqttClient
from .prometheus import PrometheusExporter
from .scanner import SwitchbotScanner
from .signals import publish_mqtt_message_request
from .store import StateStore

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, settings: AppSettings, cli_args: argparse.Namespace):
        self.settings = settings
        self.cli_args = cli_args
        self.stopping = False
        self.is_reloading = False

        setup_logging(self.settings.logging)

        self.storage = StateStore()
        self._components: Dict[str, BaseComponent] = self._create_all_components(
            self.settings
        )
        publish_mqtt_message_request.connect(self._handle_publish_request)

    def _handle_publish_request(
        self,
        sender: Any,
        topic: str,
        payload: Union[str, Dict[str, Any]],
        qos: int,
        retain: bool,
    ) -> None:
        asyncio.create_task(
            self._handle_publish_request_async(sender, topic, payload, qos, retain)
        )

    async def _handle_publish_request_async(
        self,
        sender: Any,
        topic: str,
        payload: Union[str, Dict[str, Any]],
        qos: int,
        retain: bool,
    ) -> None:
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
        mqtt_component = cast(MqttClient, self._components.get("mqtt"))
        await mqtt_component.publish(
            topic=topic, payload=payload, qos=qos, retain=retain
        )

    def _create_all_components(self, settings: AppSettings) -> Dict[str, BaseComponent]:
        """Unconditionally create all component instances."""
        components: Dict[str, BaseComponent] = {
            "scanner": SwitchbotScanner(settings=settings.scanner),
            "mqtt": MqttClient(settings.mqtt),
            "prometheus": PrometheusExporter(settings=settings.prometheus),
            "automations": AutomationHandler(
                settings=settings.automations,
                state_store=self.storage,
            ),
        }
        return components

    async def reload_settings(self):
        if self.is_reloading:
            logger.warning("Reload already in progress, ignoring request.")
            return

        logger.info("SIGHUP received, reloading configuration.")
        self.is_reloading = True
        old_settings = self.settings

        try:
            new_settings = load_settings_from_cli(self.cli_args)
            setup_logging(new_settings.logging)

            for name, component in self._components.items():
                await component.apply_new_settings(getattr(new_settings, name))

            self.settings = new_settings
            logger.info("Configuration reloaded successfully.")

        except Exception as e:
            logger.error(f"Failed to apply new configuration: {e}", exc_info=True)
            logger.info("Rolling back to the previous configuration.")

            for name, component in self._components.items():
                logger.info(f"Rolling back settings for {name}...")
                try:
                    await component.apply_new_settings(getattr(old_settings, name))
                except Exception as rollback_e:
                    logger.critical(
                        f"Failed to rollback settings for {name}: {rollback_e}. "
                        "The application is in an inconsistent state and will exit.",
                        exc_info=True,
                    )
                    sys.exit(1)

            self.settings = old_settings
            setup_logging(self.settings.logging)
            logger.info("Rollback completed.")
        finally:
            self.is_reloading = False

    async def _start_components(self, components: Dict[str, BaseComponent]) -> None:
        logger.info("Starting enabled components...")
        start_tasks = [c.start() for c in components.values()]
        if start_tasks:
            await asyncio.gather(*start_tasks)
        logger.info("Components' start sequence finished.")

    async def _stop_components(self, components: Dict[str, BaseComponent]) -> None:
        logger.info("Stopping components...")
        stop_tasks = [
            components[key].stop() for key in reversed(list(components.keys()))
        ]
        if stop_tasks:
            await asyncio.gather(*stop_tasks)
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
    except Exception as e:
        logger.critical(
            f"Application encountered a critical error and will exit: {e}",
            exc_info=True,
        )
        sys.exit(1)
    finally:
        if "app" in locals() and app:
            await app.stop()
