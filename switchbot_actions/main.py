# switchbot_actions/main.py
import argparse
import asyncio
import logging
import sys

import yaml
from switchbot import GetSwitchbotDevices

from .dispatcher import EventDispatcher
from .exporter import PrometheusExporter
from .scanner import DeviceScanner
from .store import DeviceStateStore
from .timers import TimerHandler

logger = logging.getLogger(__name__)


def setup_logging(config, debug=False):
    """Configures logging based on config file and command-line arguments."""
    if debug:
        # Debug mode: hardcode levels, ignore config
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )
        # Set bleak to INFO to reduce noise
        logging.getLogger("bleak").setLevel(logging.INFO)
        logger.info("Debug mode enabled. Root logger set to DEBUG, bleak set to INFO.")
        return

    # Normal mode: use config file
    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO")
    fmt = log_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        stream=sys.stdout,
    )

    # Apply specific logger levels from config
    for logger_name, logger_level in log_config.get("loggers", {}).items():
        logging.getLogger(logger_name).setLevel(
            getattr(logging, logger_level.upper(), logging.INFO)
        )

    logger.info(f"Logging configured with level {level}")


def load_config(path="config.yaml"):
    """Loads the configuration from a YAML file."""
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(
            f"Configuration file not found at {path}, using defaults.", file=sys.stderr
        )
        return {}
    except yaml.YAMLError as e:
        mark = getattr(e, "mark", None)
        if mark:
            print(
                f"Error parsing YAML file: {e}\n"
                f"  Line: {mark.line + 1}, Column: {mark.column + 1}",
                file=sys.stderr,
            )
        else:
            print(f"Error parsing YAML file: {e}", file=sys.stderr)
        sys.exit(1)


async def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(description="SwitchBot Prometheus Exporter")
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--scan-cycle", type=int, help="Time in seconds between BLE scan cycles"
    )
    parser.add_argument(
        "--scan-duration", type=int, help="Time in seconds to scan for BLE devices"
    )
    parser.add_argument(
        "--interface", type=str, help="Bluetooth interface to use (e.g., hci0)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config, args.debug)

    # Resolve scanner settings (CLI > config > default)
    scanner_config = config.get("scanner", {})
    scan_cycle = args.scan_cycle or scanner_config.get("cycle", 10)
    scan_duration = args.scan_duration or scanner_config.get("duration", 3)
    interface = args.interface or scanner_config.get("interface", "hci0")

    # Validate settings
    if scan_duration > scan_cycle:
        logger.error(
            f"Scan duration ({scan_duration}s) cannot be longer than "
            f"the scan cycle ({scan_cycle}s)."
        )
        sys.exit(1)

    logger.info(
        f"Scanner configured with cycle={scan_cycle}s, duration={scan_duration}s, "
        f"interface={interface}"
    )

    # Initialize core components
    store = DeviceStateStore()
    ble_scanner = GetSwitchbotDevices(interface=interface)
    scanner = DeviceScanner(
        scanner=ble_scanner, store=store, cycle=scan_cycle, duration=scan_duration
    )

    # Initialize optional components based on config
    if config.get("prometheus_exporter", {}).get("enabled", True):
        exporter_config = config.get("prometheus_exporter", {})
        exporter = PrometheusExporter(
            state_store=store,
            port=exporter_config.get("port", 8000),
            target_config=exporter_config.get("target", {}),
        )
        exporter.start_server()

    if "actions" in config and config["actions"]:
        _dispatcher = EventDispatcher(actions_config=config["actions"])

    if "timers" in config and config["timers"]:
        _timer_handler = TimerHandler(timers_config=config["timers"], store=store)

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


def cli_main():
    """Synchronous entry point for the command-line interface."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")
        sys.exit(0)


if __name__ == "__main__":
    cli_main()
