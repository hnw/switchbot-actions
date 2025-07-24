import logging
import sys

from switchbot import GetSwitchbotDevices

from .config import AppSettings
from .exporter import PrometheusExporter
from .handlers import AutomationHandler
from .scanner import DeviceScanner
from .store import StateStorage

logger = logging.getLogger(__name__)


async def run_app(settings: AppSettings):
    # Validate settings
    if settings.scanner.duration > settings.scanner.cycle:
        logger.error(
            f"Scan duration ({settings.scanner.duration}s) cannot be longer than "
            f"the scan cycle ({settings.scanner.cycle}s)."
        )
        sys.exit(1)

    logger.info(
        f"Scanner configured with cycle={settings.scanner.cycle}s, "
        f"duration={settings.scanner.duration}s, "
        f"interface={settings.scanner.interface}"
    )

    # Initialize core components
    storage = StateStorage()
    ble_scanner = GetSwitchbotDevices(interface=settings.scanner.interface)
    scanner = DeviceScanner(
        scanner=ble_scanner,
        store=storage,
        cycle=settings.scanner.cycle,
        duration=settings.scanner.duration,
    )

    # Initialize optional components based on config
    if settings.prometheus_exporter.enabled:
        exporter = PrometheusExporter(
            state_storage=storage,
            port=settings.prometheus_exporter.port,
            target_config=settings.prometheus_exporter.target,
        )
        exporter.start_server()

    if settings.automations:
        logger.info(f"Registering {len(settings.automations)} automations.")
        _automation_handler = AutomationHandler(configs=settings.automations)

    # Start the main scanning loop
    logger.info("Starting SwitchBot BLE scanner...")
    try:
        await scanner.start_scan()
    except KeyboardInterrupt:
        logger.info("Stopping scanner...")
        await scanner.stop_scan()
        logger.info("Scanner stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
