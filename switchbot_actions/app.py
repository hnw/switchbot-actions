import asyncio
import logging
import signal

import yaml
from pydantic import ValidationError
from switchbot import GetSwitchbotDevices

from .config import AppSettings
from .exporter import PrometheusExporter
from .handlers import AutomationHandler
from .mqtt import MqttClient
from .scanner import SwitchbotClient
from .signals import publish_mqtt_message_request
from .store import StateStore

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.tasks: list[asyncio.Task] = []
        self.stopping = False

        # Initialize core components
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
        self.automation_handler: AutomationHandler | None = None
        self.exporter: PrometheusExporter | None = None

        self._configure_components()

    def _configure_components(self):
        """Configure or reconfigure components based on current settings."""
        # Initialize MQTT client if configured
        if self.settings.mqtt:
            if not self.mqtt_client:
                self.mqtt_client = MqttClient(self.settings.mqtt)
                publish_mqtt_message_request.connect(self._handle_mqtt_publish)
        else:
            if self.mqtt_client:
                publish_mqtt_message_request.disconnect(self._handle_mqtt_publish)
                self.mqtt_client = None

        # Initialize optional components based on config
        if self.settings.prometheus_exporter.enabled:
            if not self.exporter:
                self.exporter = PrometheusExporter(
                    state_storage=self.storage,
                    port=self.settings.prometheus_exporter.port,
                    target_config=self.settings.prometheus_exporter.target,
                )
                self.exporter.start_server()
        elif self.exporter:
            # TODO: Implement stop server functionality if needed
            pass

        if self.settings.automations:
            logger.info(f"Registering {len(self.settings.automations)} automations.")
            self.automation_handler = AutomationHandler(
                configs=self.settings.automations
            )
        else:
            self.automation_handler = None

    def _handle_mqtt_publish(self, sender, **kwargs):
        if self.mqtt_client:
            asyncio.create_task(self.mqtt_client.publish(**kwargs))

    def reload_settings(self):
        """Reload settings from the configuration file."""
        logger.info("SIGHUP received, reloading configuration.")
        try:
            with open(self.settings.config_path, "r") as f:
                config_data = yaml.safe_load(f) or {}
            new_settings = AppSettings.model_validate(config_data)
        except FileNotFoundError:
            logger.error(
                f"Configuration file not found at {self.settings.config_path}, "
                f"keeping the old one."
            )
            return
        except yaml.YAMLError as e:
            mark = getattr(e, "mark", None)
            if mark:
                logger.error(
                    f"Error parsing YAML file: {e}\n"
                    f"  Line: {mark.line + 1}, Column: {mark.column + 1}"
                )
            else:
                logger.error(f"Error parsing YAML file: {e}")
            logger.error("Failed to parse new configuration, keeping the old one.")
            return
        except ValidationError as e:
            logger.error(f"Configuration validation error during reload: {e}")
            logger.error("Failed to validate new configuration, keeping the old one.")
            return

        self.settings = new_settings
        self._configure_components()
        logger.info("Configuration reloaded successfully.")

    async def start(self):
        """Start the application and its background tasks."""
        logger.info("Starting SwitchBot BLE scanner...")
        if self.mqtt_client:
            self.tasks.append(asyncio.create_task(self.mqtt_client.run()))

        self.tasks.append(asyncio.create_task(self.scanner.start_scan()))

        await asyncio.gather(*self.tasks)

    async def stop(self):
        """Stop the application and clean up resources."""
        if self.stopping:
            return
        self.stopping = True

        logger.info("Stopping application...")
        await self.scanner.stop_scan()

        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("Application stopped.")


async def run_app(settings: AppSettings):
    app = Application(settings)
    loop = asyncio.get_running_loop()

    # Set up signal handlers
    loop.add_signal_handler(signal.SIGHUP, app.reload_settings)

    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        await app.stop()
