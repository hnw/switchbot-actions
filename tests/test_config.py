import pytest
from pydantic import ValidationError

from switchbot_actions.config import (
    AppSettings,
    AutomationIf,
    AutomationRule,
    LoggingSettings,
    MqttSettings,
    PrometheusExporterSettings,
    ScannerSettings,
    ShellCommandAction,
    WebhookAction,
)


def test_mqtt_settings_defaults():
    settings = MqttSettings(host="localhost")
    assert settings.host == "localhost"
    assert settings.port == 1883
    assert settings.username is None
    assert settings.password is None
    assert settings.reconnect_interval == 10


def test_prometheus_exporter_settings_defaults():
    settings = PrometheusExporterSettings()
    assert settings.enabled is False
    assert settings.port == 8000
    assert settings.target == {}


def test_scanner_settings_defaults():
    settings = ScannerSettings()
    assert settings.cycle == 10
    assert settings.duration == 3
    assert settings.interface == 0


def test_scanner_settings_duration_validation():
    with pytest.raises(
        ValidationError,
        match="scanner.duration must be less than or equal to scanner.cycle",
    ):
        ScannerSettings(cycle=5, duration=6)


def test_logging_settings_defaults():
    settings = LoggingSettings()
    assert settings.level == "INFO"
    assert settings.format == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    assert settings.loggers == {}


@pytest.mark.parametrize(
    "level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]
)
def test_logging_settings_valid_levels(level):
    settings = LoggingSettings(level=level)
    assert settings.level == level


def test_logging_settings_invalid_level():
    with pytest.raises(ValidationError):
        LoggingSettings(level="INVALID_LEVEL")  # type: ignore


def test_automation_if_timer_source_requires_duration():
    # Valid case
    AutomationIf(source="switchbot_timer", duration=10)
    AutomationIf(source="mqtt_timer", duration=5)
    AutomationIf(source="some_other_source")  # No duration required

    # Invalid cases
    with pytest.raises(
        ValidationError, match="'duration' is required for source 'switchbot_timer'"
    ):
        AutomationIf(source="switchbot_timer")
    with pytest.raises(
        ValidationError, match="'duration' is required for source 'mqtt_timer'"
    ):
        AutomationIf(source="mqtt_timer")


def test_automation_rule_then_block_single_dict_to_list():
    rule = AutomationRule.model_validate(
        {
            "if": {"source": "test"},
            "then": {"type": "shell_command", "command": "echo hello"},
        }
    )
    assert isinstance(rule.then_block, list)
    assert len(rule.then_block) == 1
    assert isinstance(rule.then_block[0], ShellCommandAction)
    assert rule.then_block[0].command == "echo hello"


def test_automation_rule_then_block_already_list():
    rule = AutomationRule.model_validate(
        {
            "if": {"source": "test"},
            "then": [
                {"type": "shell_command", "command": "echo hello"},
                {"type": "webhook", "url": "http://example.com"},
            ],
        }
    )
    assert isinstance(rule.then_block, list)
    assert len(rule.then_block) == 2
    assert isinstance(rule.then_block[0], ShellCommandAction)
    assert rule.then_block[0].command == "echo hello"
    assert isinstance(rule.then_block[1], WebhookAction)
    assert rule.then_block[1].url == "http://example.com"


def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.config_path == "config.yaml"
    assert settings.debug is False
    assert isinstance(settings.scanner, ScannerSettings)
    assert isinstance(settings.prometheus_exporter, PrometheusExporterSettings)
    assert settings.automations == []
    assert isinstance(settings.logging, LoggingSettings)
    assert settings.mqtt is None


def test_app_settings_from_dict():
    config_data = {
        "debug": True,
        "scanner": {"cycle": 20, "duration": 5},
        "mqtt": {"host": "test.mqtt.org"},
        "automations": [
            {
                "if": {"source": "switchbot_timer", "duration": 60},
                "then": [{"type": "webhook", "url": "http://example.com/turn_on"}],
            }
        ],
    }
    settings = AppSettings.model_validate(config_data)

    assert settings.debug is True
    assert settings.scanner.cycle == 20
    assert settings.scanner.duration == 5
    assert settings.mqtt is not None
    assert settings.mqtt.host == "test.mqtt.org"
    assert len(settings.automations) == 1
    assert settings.automations[0].if_block.source == "switchbot_timer"
    assert settings.automations[0].if_block.duration == 60
    assert isinstance(settings.automations[0].then_block[0], WebhookAction)
    assert settings.automations[0].then_block[0].url == "http://example.com/turn_on"


def test_app_settings_invalid_config_data():
    invalid_config_data = {
        "scanner": {"cycle": 5, "duration": 10},  # Invalid duration
    }
    with pytest.raises(ValidationError):
        AppSettings.model_validate(invalid_config_data)

    invalid_config_data = {
        "logging": {"level": "BAD_LEVEL"},  # Invalid log level
    }
    with pytest.raises(ValidationError):
        AppSettings.model_validate(invalid_config_data)

    invalid_config_data = {
        "automations": [
            {
                "if": {"source": "switchbot_timer"},  # Missing duration
                "then": [{"type": "webhook", "url": "http://example.com/turn_on"}],
            }
        ],
    }
    with pytest.raises(ValidationError):
        AppSettings.model_validate(invalid_config_data)

    # Test case for invalid action structure within then_block
    invalid_config_data = {
        "automations": [
            {
                "if": {"source": "some_source"},
                "then": [{"action": "not_a_dict"}],  # Invalid: action should be a dict
            }
        ],
    }
    with pytest.raises(ValidationError):
        AppSettings.model_validate(invalid_config_data)
