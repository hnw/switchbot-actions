import argparse
import asyncio
import logging
import signal
import sys

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


class Application:
    def __init__(self, settings: AppSettings, cli_args: argparse.Namespace):
        self.settings = settings
        self.cli_args = cli_args
        self.tasks: list[asyncio.Task] = []
        self.stopping = False

        setup_logging(self.settings)

        self.storage = StateStore()
        self.ble_scanner = GetSwitchbotDevices(
            interface=self.settings.scanner.interface
        )
        self.scanner = SwitchbotClient(
            scanner=self.ble_scanner,
            store=self.storage,
            cycle=self.settings.scanner.cycle,
            duration=self.settings.scanner.duration,
        )
        self.mqtt_client: MqttClient | None = None
        self.mqtt_task: asyncio.Task | None = None
        self.automation_handler: AutomationHandler | None = None
        self.exporter: PrometheusExporter | None = None

        self._start_components()

    def _start_mqtt(self):
        if self.settings.mqtt:
            logger.info("Starting MQTT client.")
            self.mqtt_client = MqttClient(self.settings.mqtt)
            publish_mqtt_message_request.connect(self._handle_mqtt_publish)
            self.mqtt_task = asyncio.create_task(self.mqtt_client.run())

    async def _stop_mqtt(self):
        if not self.mqtt_client:
            return

        logger.info("Stopping MQTT client.")
        publish_mqtt_message_request.disconnect(self._handle_mqtt_publish)

        if self.mqtt_task and not self.mqtt_task.done():
            self.mqtt_task.cancel()
            try:
                await self.mqtt_task
            except asyncio.CancelledError:
                logger.info("MQTT client task successfully cancelled.")

        await self.mqtt_client.stop()
        self.mqtt_client = None
        self.mqtt_task = None

    def _start_exporter(self):
        if self.settings.prometheus_exporter.enabled:
            logger.info("Starting Prometheus exporter.")
            self.exporter = PrometheusExporter(
                settings=self.settings.prometheus_exporter
            )
            self.exporter.start()

    def _stop_exporter(self):
        if self.exporter:
            logger.info("Stopping Prometheus exporter.")
            self.exporter.stop()
            self.exporter = None

    def _start_automations(self):
        if self.settings.automations:
            logger.info(f"Registering {len(self.settings.automations)} automations.")
            self.automation_handler = AutomationHandler(
                configs=self.settings.automations, state_store=self.storage
            )

    def _stop_automations(self):
        if self.automation_handler:
            logger.info("Stopping automations.")
            self.automation_handler = None

    def _start_components(self):
        self._start_mqtt()
        self._start_exporter()
        self._start_automations()

    async def _stop_components(self):
        await self._stop_mqtt()
        self._stop_exporter()
        self._stop_automations()

    def _handle_mqtt_publish(self, sender, **kwargs):
        if self.mqtt_client:
            asyncio.create_task(self.mqtt_client.publish(**kwargs))

    async def reload_settings(self):
        logger.info("SIGHUP received, reloading configuration.")
        try:
            new_settings = load_settings_from_cli(self.cli_args)
        except ConfigError as e:
            logger.error(
                f"Failed to load new configuration, keeping the old. Reason:\n{e}"
            )
            return
        except Exception as e:
            logger.error(
                f"Unexpected error loading new configuration: {e}", exc_info=True
            )
            return

        setup_logging(new_settings)

        changed_components = self._get_changed_components(self.settings, new_settings)
        if not changed_components:
            logger.info("No configuration changes detected.")
            return

        logger.info(f"Configuration changed for: {', '.join(changed_components)}")
        old_settings = self.settings

        try:
            # Stop changed components first
            await self._stop_changed_components(changed_components)

            # Try to start components with the new settings
            self.settings = new_settings
            self._start_changed_components(changed_components)

            logger.info("Configuration reloaded and components restarted successfully.")
        except Exception as e:
            logger.error(f"Failed to apply new configuration: {e}", exc_info=True)
            logger.info("Rolling back to the previous configuration.")
            self.settings = old_settings  # Rollback to old settings
            try:
                # Restart components with the old settings
                self._start_changed_components(changed_components)
                logger.info("Rollback successful.")
            except Exception as rollback_e:
                logger.critical(f"Rollback failed: {rollback_e}", exc_info=True)
                logger.debug("Exiting due to rollback failure.", exc_info=True)
                sys.exit(1)

    def _get_changed_components(self, old: AppSettings, new: AppSettings) -> list[str]:
        changed = []
        if old.mqtt != new.mqtt:
            changed.append("mqtt")
        if old.prometheus_exporter != new.prometheus_exporter:
            changed.append("exporter")
        if old.automations != new.automations:
            changed.append("automations")
        return changed

    async def _stop_changed_components(self, changed_components: list[str]):
        if "mqtt" in changed_components:
            await self._stop_mqtt()
        if "exporter" in changed_components:
            self._stop_exporter()
        if "automations" in changed_components:
            self._stop_automations()

    def _start_changed_components(self, changed_components: list[str]):
        if "mqtt" in changed_components:
            self._start_mqtt()
        if "exporter" in changed_components:
            self._start_exporter()
        if "automations" in changed_components:
            self._start_automations()

    async def start(self):
        logger.info("Starting SwitchBot BLE scanner...")
        self.tasks.append(asyncio.create_task(self.scanner.start_scan()))
        if self.mqtt_task:
            self.tasks.append(self.mqtt_task)
        await asyncio.gather(*self.tasks)

    async def stop(self):
        if self.stopping:
            return
        self.stopping = True

        logger.info("Stopping application...")
        self.scanner.stop_scan()
        await self._stop_components()

        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("Application stopped.")


async def run_app(settings: AppSettings, args: argparse.Namespace):
    app = None  # Initialize app to None
    try:
        app = Application(settings, args)
        loop = asyncio.get_running_loop()

        loop.add_signal_handler(
            signal.SIGHUP, lambda: asyncio.create_task(app.reload_settings())
        )

        await app.start()
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
        # If app failed to initialize, it won't be defined.
        if "app" in locals() and app:
            await app.stop()
