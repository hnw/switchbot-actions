import argparse
import asyncio
import logging
import sys
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .app import run_app
from .config import AppSettings, MqttSettings
from .error import format_validation_error
from .logging import setup_logging

logger = logging.getLogger(__name__)


def cli_main():
    """Synchronous entry point for the command-line interface."""
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
        "--interface",
        type=int,
        help="Bluetooth adapter number to use (e.g., 0 for hci0, 1 for hci1)",
    )
    parser.add_argument(
        "--prometheus-exporter-enabled",
        action="store_true",
        help="Enable Prometheus exporter",
    )
    parser.add_argument(
        "--prometheus-exporter-port", type=int, help="Prometheus exporter port"
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
    args = parser.parse_args()

    config_data = {}
    yaml = YAML(typ="rt")
    config_path = Path(args.config)
    try:
        with open(config_path, "r") as f:
            config_data = yaml.load(f) or {}
    except FileNotFoundError:
        print(
            f"Configuration file not found at {config_path}, using defaults.",
            file=sys.stderr,
        )
        config_data = {}
    except YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        if mark:
            print(
                f"Error parsing YAML file: {e}\n"
                f"  in {config_path}, line: {mark.line + 1}, column: {mark.column + 1}",
                file=sys.stderr,
            )
        else:
            print(f"Error parsing YAML file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        config_data["config_path"] = args.config
        settings = AppSettings.model_validate(config_data)
    except ValidationError as e:
        error_message = format_validation_error(e, config_path, config_data)
        print(error_message, file=sys.stderr)
        sys.exit(1)

    # Apply CLI arguments, overriding config file settings
    if args.debug:
        settings.debug = args.debug
    if args.scan_cycle is not None:
        settings.scanner.cycle = args.scan_cycle
    if args.scan_duration is not None:
        settings.scanner.duration = args.scan_duration
    if args.interface is not None:
        settings.scanner.interface = args.interface
    if args.prometheus_exporter_enabled:
        settings.prometheus_exporter.enabled = args.prometheus_exporter_enabled
    if args.prometheus_exporter_port is not None:
        settings.prometheus_exporter.port = args.prometheus_exporter_port
    if args.mqtt_host is not None:
        if settings.mqtt is None:
            settings.mqtt = MqttSettings(host=args.mqtt_host)  # type: ignore[call-arg]
        else:
            settings.mqtt.host = args.mqtt_host
    if args.mqtt_port is not None:
        if settings.mqtt is None:
            settings.mqtt = MqttSettings(port=args.mqtt_port, host="localhost")
        else:
            settings.mqtt.port = args.mqtt_port
    if args.mqtt_username is not None:
        if settings.mqtt is None:
            settings.mqtt = MqttSettings(username=args.mqtt_username, host="localhost")  # type: ignore[call-arg]
        else:
            settings.mqtt.username = args.mqtt_username
    if args.mqtt_password is not None:
        if settings.mqtt is None:
            settings.mqtt = MqttSettings(password=args.mqtt_password, host="localhost")  # type: ignore[call-arg]
        else:
            settings.mqtt.password = args.mqtt_password
    if args.mqtt_reconnect_interval is not None:
        if settings.mqtt is None:
            settings.mqtt = MqttSettings(
                reconnect_interval=args.mqtt_reconnect_interval, host="localhost"
            )  # type: ignore[call-arg]
        else:
            settings.mqtt.reconnect_interval = args.mqtt_reconnect_interval
    if args.log_level is not None:
        settings.logging.level = args.log_level

    setup_logging(settings)

    try:
        asyncio.run(run_app(settings))
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")
        sys.exit(0)
