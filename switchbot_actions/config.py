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
    enabled: bool = True
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
    def load_from_yaml(cls, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
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
            sys.exit(1)

    def apply_cli_args(self, args: argparse.Namespace):
        if args.debug:
            self.debug = True
        if args.scan_cycle is not None:
            self.scanner.cycle = args.scan_cycle
        if args.scan_duration is not None:
            self.scanner.duration = args.scan_duration
        if args.interface is not None:
            self.scanner.interface = args.interface

    @classmethod
    def from_args(cls, args: argparse.Namespace):
        config_data = cls.load_from_yaml(args.config)

        # Initialize with defaults and then override with config file values
        settings = cls(config_path=args.config)

        # Manually merge nested dictionaries
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

        settings.apply_cli_args(args)

        return settings
