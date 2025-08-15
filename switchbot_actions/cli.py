import argparse
import asyncio
import logging
import sys

from .app import run_app
from .config_loader import load_settings_from_cli
from .error import ConfigError

logger = logging.getLogger(__name__)


def cli_main():
    """Synchronous entry point for the command-line interface."""
    parser = argparse.ArgumentParser(
        description="A YAML-based automation engine for SwitchBot BLE devices."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action=argparse.BooleanOptionalAction,
        help="Enable debug logging",
    )
    parser.add_argument(
        "--scan-cycle", type=int, help="Time in seconds between BLE scan cycles"
    )
    parser.add_argument(
        "--scan-duration", type=int, help="Time in seconds to scan for BLE devices"
    )
    parser.add_argument(
        "--interface",
        type=int,
        help="Bluetooth adapter number to use (e.g., 0 for hci0, 1 for hci1)",
    )
    parser.add_argument(
        "--prometheus-enabled",
        action=argparse.BooleanOptionalAction,
        help="Enable Prometheus exporter",
    )
    parser.add_argument(
        "--prometheus-port",
        type=int,
        help="Prometheus exporter port",
        metavar="PORT",
    )
    parser.add_argument("--mqtt-host", type=str, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, help="MQTT broker username")
    parser.add_argument("--mqtt-password", type=str, help="MQTT broker password")
    parser.add_argument(
        "--mqtt-reconnect-interval", type=int, help="MQTT broker reconnect interval"
    )
    parser.add_argument(
        "--log-level", type=str, help="Set the logging level (e.g., INFO, DEBUG)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check the configuration and exit without running the application.",
    )
    args = parser.parse_args()

    try:
        settings = load_settings_from_cli(args)
    except ConfigError as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        print("Configuration is valid.")
        sys.exit(0)

    try:
        asyncio.run(run_app(settings, args))
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")
        sys.exit(0)
