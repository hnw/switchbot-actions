# switchbot_exporter/main.py
import asyncio
import logging
import yaml
import sys

from .manager import SwitchbotManager
from .store import DeviceStateStore
from .exporter import PrometheusExporter
from .dispatcher import EventDispatcher
from switchbot import GetSwitchbotDevices

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def load_config(path='config.yaml'):
    """Loads the configuration from a YAML file."""
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {path}. Please create it from config.yaml.example.")
        sys.exit(1)
    except yaml.YAMLError as e:
        if hasattr(e, 'mark'):
            mark = e.mark
            logger.error(f"Error parsing YAML file: {e}\n  Line: {mark.line + 1}, Column: {mark.column + 1}")
        else:
            logger.error(f"Error parsing YAML file: {e}")
        sys.exit(1)

async def main():
    """Main entry point for the application."""
    config = load_config()

    # Initialize core components
    store = DeviceStateStore()
    scanner = GetSwitchbotDevices()
    manager = SwitchbotManager(scanner=scanner)

    # Initialize optional components based on config
    if config.get('prometheus_exporter', {}).get('enabled', True):
        exporter_config = config.get('prometheus_exporter', {})
        exporter = PrometheusExporter(
            state_store=store,
            port=exporter_config.get('port', 8000),
            target_config=exporter_config.get('target', {})
        )
        exporter.start_server()
        logger.info(f"Prometheus exporter started on port {exporter.port}")

    if 'actions' in config and config['actions']:
        dispatcher = EventDispatcher(actions_config=config['actions'])
        logger.info(f"Event dispatcher initialized with {len(config['actions'])} actions.")

    # Start the main scanning loop
    logger.info("Starting SwitchBot BLE scanner...")
    try:
        await manager.start_scan()
    except KeyboardInterrupt:
        logger.info("Stopping scanner...")
        await manager.stop_scan()
        logger.info("Scanner stopped.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)

if __name__ == '__main__':
    asyncio.run(main())
