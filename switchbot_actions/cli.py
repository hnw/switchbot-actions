import argparse
import asyncio
import logging
import sys
from importlib.metadata import PackageNotFoundError, version

from .app import run_app
from .config import AppSettings
from .config_loader import load_settings_from_cli
from .error import ConfigError

logger = logging.getLogger(__name__)

DEFAULTS = AppSettings()


def cli_main():
    """Synchronous entry point for the command-line interface."""
    try:
        app_version = version("switchbot-actions")
    except PackageNotFoundError:
        app_version = "unknown"

    parser = argparse.ArgumentParser(
        description="A YAML-based automation engine for SwitchBot BLE devices."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {app_version}"
    )

    # General settings
    general_group = parser.add_argument_group("General Settings")
    general_group.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path to the configuration file. (default: config.yaml)",
        metavar="PATH",
    )
    general_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (-v: automation, -vv: app, -vvv: full debug).",
    )
    general_group.add_argument(
        "--check",
        action="store_true",
        help="Check the configuration and exit without running.",
    )

    # Scanner settings
    scanner_group = parser.add_argument_group("Scanner Settings")
    scanner_group.add_argument(
        "--scanner",
        dest="scanner_enabled",
        action="store_true",
        default=None,
        help=f"Enable SwitchBot BLE scanner. "
        f"(default: {'enabled' if DEFAULTS.scanner.enabled else 'disabled'})",
    )
    scanner_group.add_argument(
        "--no-scanner",
        dest="scanner_enabled",
        action="store_false",
        default=None,
        help="Disable SwitchBot BLE scanner.",
    )
    scanner_group.add_argument(
        "--scanner-wait",
        type=int,
        default=None,
        help=f"Time to wait between BLE scan durations. "
        f"(default: {DEFAULTS.scanner.wait})",
        metavar="SECONDS",
    )
    scanner_group.add_argument(
        "--scanner-duration",
        type=int,
        default=None,
        help=f"Time to scan for BLE devices. (default: {DEFAULTS.scanner.duration})",
        metavar="SECONDS",
    )
    scanner_group.add_argument(
        "--scanner-interface",
        type=int,
        help="Bluetooth adapter number (e.g., 0 for hci0).",
        metavar="ADAPTER",
    )

    # Prometheus settings
    prometheus_group = parser.add_argument_group("Prometheus Settings")
    prometheus_group.add_argument(
        "--prometheus",
        dest="prometheus_enabled",
        action="store_true",
        default=None,
        help=f"Enable Prometheus exporter. "
        f"(default: {'enabled' if DEFAULTS.prometheus.enabled else 'disabled'})",
    )
    prometheus_group.add_argument(
        "--no-prometheus",
        dest="prometheus_enabled",
        action="store_false",
        default=None,
        help="Disable Prometheus exporter.",
    )
    prometheus_group.add_argument(
        "--prometheus-port",
        type=int,
        default=None,
        help=f"Prometheus exporter port. (default: {DEFAULTS.prometheus.port})",
        metavar="PORT",
    )

    # MQTT settings
    mqtt_group = parser.add_argument_group("MQTT Settings")
    mqtt_group.add_argument(
        "--mqtt",
        dest="mqtt_enabled",
        action="store_true",
        default=None,
        help=f"Enable MQTT client. "
        f"(default: {'enabled' if DEFAULTS.mqtt.enabled else 'disabled'})",
    )
    mqtt_group.add_argument(
        "--no-mqtt",
        dest="mqtt_enabled",
        action="store_false",
        default=None,
        help="Disable MQTT client.",
    )
    mqtt_group.add_argument(
        "--mqtt-host",
        type=str,
        default=None,
        help=f'MQTT broker host. (default: "{DEFAULTS.mqtt.host}")',
        metavar="HOST",
    )
    mqtt_group.add_argument(
        "--mqtt-port",
        type=int,
        default=None,
        help=f"MQTT broker port. (default: {DEFAULTS.mqtt.port})",
        metavar="PORT",
    )
    mqtt_group.add_argument(
        "--mqtt-username", type=str, help="MQTT broker username.", metavar="USER"
    )
    mqtt_group.add_argument(
        "--mqtt-password", type=str, help="MQTT broker password.", metavar="PASS"
    )
    mqtt_group.add_argument(
        "--mqtt-reconnect-interval",
        type=float,
        default=None,
        help=f"MQTT broker reconnect interval. "
        f"(default: {DEFAULTS.mqtt.reconnect_interval})",
        metavar="SECONDS",
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


if __name__ == "__main__":
    cli_main()
