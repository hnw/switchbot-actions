# switchbot_actions/config_loader.py
import argparse
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from .config import AppSettings
from .error import ConfigError, format_validation_error, get_error_snippet


def _set_nested_value(d: dict, key_path: str, value: Any):
    keys = key_path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def load_settings_from_cli(args: argparse.Namespace) -> AppSettings:
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
    except YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        problem = getattr(e, "problem", e)
        if mark:
            error_messages = [f"YAML Parsing Error in '{config_path}':"]
            snippet = get_error_snippet(config_path, (mark.line, mark.column))
            if snippet:
                error_messages.append("")
                error_messages.append(snippet)

            error_messages.append("")
            error_messages.append(f"Error at line {mark.line + 1}: {problem}")
            raise ConfigError("\n".join(error_messages))
        else:
            raise ConfigError(f"YAML Parsing Error: {problem}")

    cli_to_config_map = {
        "debug": "debug",
        "scan_cycle": "scanner.cycle",
        "scan_duration": "scanner.duration",
        "interface": "scanner.interface",
        "prometheus_exporter_enabled": "prometheus_exporter.enabled",
        "prometheus_exporter_port": "prometheus_exporter.port",
        "mqtt_host": "mqtt.host",
        "mqtt_port": "mqtt.port",
        "mqtt_username": "mqtt.username",
        "mqtt_password": "mqtt.password",
        "mqtt_reconnect_interval": "mqtt.reconnect_interval",
        "log_level": "logging.level",
    }

    for arg_key, key_path in cli_to_config_map.items():
        value = getattr(args, arg_key, None)
        if value is not None:
            _set_nested_value(config_data, key_path, value)

    try:
        settings = AppSettings.model_validate(config_data)
        return settings
    except ValidationError as e:
        error_message = format_validation_error(e, config_path, config_data)
        raise ConfigError(error_message)
