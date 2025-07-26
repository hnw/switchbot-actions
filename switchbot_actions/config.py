import argparse
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

import yaml


@dataclass
class MqttSettings:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    reconnect_interval: int = 10


@dataclass
class PrometheusExporterSettings:
    enabled: bool = False
    port: int = 8000
    target: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScannerSettings:
    cycle: int = 10
    duration: int = 3
    interface: int = 0


@dataclass
class LoggingSettings:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loggers: Dict[str, str] = field(default_factory=dict)


@dataclass
class AppSettings:
    config_path: str = "config.yaml"
    debug: bool = False
    scanner: ScannerSettings = field(default_factory=ScannerSettings)
    prometheus_exporter: PrometheusExporterSettings = field(
        default_factory=PrometheusExporterSettings
    )
    automations: List[Dict[str, Any]] = field(default_factory=list)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    mqtt: MqttSettings | None = None

    @classmethod
    def load_from_yaml(cls, path: str) -> Dict[str, Any] | None:
        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
                if config is None:  # Handle empty file
                    return {}
                return config
        except FileNotFoundError:
            print(
                f"Configuration file not found at {path}, using defaults.",
                file=sys.stderr,
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
            return None

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        if args.debug is not None:
            self.debug = args.debug
        if args.config is not None:
            self.config_path = args.config

        # Apply scanner settings
        if args.scan_cycle is not None:
            self.scanner.cycle = args.scan_cycle
        if args.scan_duration is not None:
            self.scanner.duration = args.scan_duration
        if args.interface is not None:
            self.scanner.interface = args.interface

        # Apply prometheus exporter settings
        if args.prometheus_exporter_enabled is not None:
            self.prometheus_exporter.enabled = args.prometheus_exporter_enabled
        if args.prometheus_exporter_port is not None:
            self.prometheus_exporter.port = args.prometheus_exporter_port

        # Apply MQTT settings
        if args.mqtt_host is not None:
            if self.mqtt is None:
                self.mqtt = MqttSettings(host=args.mqtt_host)
            else:
                self.mqtt.host = args.mqtt_host
        if args.mqtt_port is not None:
            if self.mqtt is None:
                self.mqtt = MqttSettings(
                    port=args.mqtt_port, host="localhost"
                )  # Default host if only port is provided
            else:
                self.mqtt.port = args.mqtt_port
        if args.mqtt_username is not None:
            if self.mqtt is None:
                self.mqtt = MqttSettings(username=args.mqtt_username, host="localhost")
            else:
                self.mqtt.username = args.mqtt_username
        if args.mqtt_password is not None:
            if self.mqtt is None:
                self.mqtt = MqttSettings(password=args.mqtt_password, host="localhost")
            else:
                self.mqtt.password = args.mqtt_password
        if args.mqtt_reconnect_interval is not None:
            if self.mqtt is None:
                self.mqtt = MqttSettings(
                    reconnect_interval=args.mqtt_reconnect_interval, host="localhost"
                )
            else:
                self.mqtt.reconnect_interval = args.mqtt_reconnect_interval

        # Apply logging settings
        if args.log_level is not None:
            self.logging.level = args.log_level

    @classmethod
    def from_config_dict(
        cls, config_data: Dict[str, Any], config_path: str
    ) -> "AppSettings":
        """Create an AppSettings instance from a dictionary."""
        settings = cls(config_path=config_path)

        if "scanner" in config_data:
            settings.scanner = ScannerSettings(**config_data["scanner"])
        if "prometheus_exporter" in config_data:
            settings.prometheus_exporter = PrometheusExporterSettings(
                **config_data["prometheus_exporter"]
            )
        if "logging" in config_data:
            settings.logging = LoggingSettings(**config_data["logging"])
        if "mqtt" in config_data:
            settings.mqtt = MqttSettings(**config_data["mqtt"])
        if "automations" in config_data:
            settings.automations = config_data["automations"]

        return settings

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "AppSettings":
        config_data = cls.load_from_yaml(args.config)
        if config_data is None:
            sys.exit(1)

        settings = cls.from_config_dict(config_data, args.config)
        settings.apply_cli_args(args)

        return settings
