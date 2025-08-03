import pytest
from pydantic import ValidationError

from switchbot_actions.config import (
    AppSettings,
    AutomationIf,
    AutomationRule,
    LoggingSettings,
    MqttPublishAction,
    MqttSettings,
    PrometheusExporterSettings,
    ScannerSettings,
    ShellCommandAction,
    WebhookAction,
)


def test_mqtt_settings_defaults():
    settings = MqttSettings(host="localhost")  # type: ignore[call-arg]
    assert settings.host == "localhost"
    assert settings.port == 1883
    assert settings.username is None
    assert settings.password is None
    assert settings.reconnect_interval == 10


@pytest.mark.parametrize("port", [0, 65536])
def test_mqtt_settings_invalid_port(port):
    with pytest.raises(ValidationError):
        MqttSettings(host="localhost", port=port)


def test_prometheus_exporter_settings_defaults():
    settings = PrometheusExporterSettings()  # type: ignore[call-arg]
    assert settings.enabled is False
    assert settings.port == 8000
    assert settings.target == {}


@pytest.mark.parametrize("port", [0, 65536])
def test_prometheus_exporter_settings_invalid_port(port):
    with pytest.raises(ValidationError):
        PrometheusExporterSettings(port=port)


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


def test_automation_if_backward_compatibility():
    # Old format using device and state
    with pytest.warns(DeprecationWarning):
        if_config_old = AutomationIf(
            source="switchbot",
            device={"address": "A"},
            state={"temperature": "> 25"},
        )
    assert if_config_old.conditions == {
        "address": "A",
        "temperature": "> 25",
    }
    assert if_config_old.device is None
    assert if_config_old.state is None

    # New format using conditions
    if_config_new = AutomationIf(
        source="switchbot",
        conditions={"address": "A", "temperature": "> 25"},
    )
    assert if_config_new.conditions == {
        "address": "A",
        "temperature": "> 25",
    }

    # Mixed format
    with pytest.warns(DeprecationWarning):
        if_config_mixed = AutomationIf(
            source="switchbot",
            device={"address": "A"},
            conditions={"temperature": "> 25"},
        )
    assert if_config_mixed.conditions == {
        "address": "A",
        "temperature": "> 25",
    }


def test_automation_if_timer_source_requires_duration():
    # Valid case
    AutomationIf(source="switchbot_timer", duration=10)
    AutomationIf(source="mqtt_timer", duration=5, topic="a/b")
    AutomationIf(source="switchbot")  # No duration required

    # Invalid cases
    with pytest.raises(
        ValidationError, match="'duration' is required for source 'switchbot_timer'"
    ):
        AutomationIf(source="switchbot_timer")
    with pytest.raises(
        ValidationError, match="'duration' is required for source 'mqtt_timer'"
    ):
        AutomationIf(source="mqtt_timer", topic="a/b")


def test_automation_if_mqtt_source_requires_topic():
    # Valid case
    AutomationIf(source="mqtt", topic="test/topic")
    AutomationIf(source="mqtt_timer", topic="test/topic", duration=1)
    AutomationIf(source="switchbot")  # No topic required

    # Invalid cases
    with pytest.raises(ValidationError, match="'topic' is required for source 'mqtt'"):
        AutomationIf(source="mqtt")
    with pytest.raises(
        ValidationError, match="'topic' is required for source 'mqtt_timer'"
    ):
        AutomationIf(source="mqtt_timer", duration=1)


@pytest.mark.parametrize("method_in, method_out", [("post", "POST"), ("get", "GET")])
def test_webhook_action_method_case_insensitivity(method_in, method_out):
    action = WebhookAction(type="webhook", url="http://example.com", method=method_in)
    assert action.method == method_out


def test_webhook_action_invalid_method():
    with pytest.raises(ValidationError, match="method must be POST or GET"):
        WebhookAction(type="webhook", url="http://example.com", method="PUT")


@pytest.mark.parametrize("qos", [0, 1, 2])
def test_mqtt_publish_action_valid_qos(qos):
    action = MqttPublishAction(type="mqtt_publish", topic="a/b", qos=qos)
    assert action.qos == qos


def test_mqtt_publish_action_invalid_qos():
    with pytest.raises(ValidationError):
        MqttPublishAction(type="mqtt_publish", topic="a/b", qos=3)  # type: ignore[arg-type]


def test_automation_rule_then_block_single_dict_to_list():
    rule = AutomationRule.model_validate(
        {
            "if": {"source": "switchbot"},
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
            "if": {"source": "switchbot"},
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
    assert (
        str(settings.automations[0].then_block[0].url) == "http://example.com/turn_on"
    )


def test_automation_rule_if_block_name_assignment():
    # Test with rule name provided
    rule_with_name = AutomationRule.model_validate(
        {
            "name": "MyRule",
            "if": {"source": "switchbot"},
            "then": [{"type": "shell_command", "command": "echo hello"}],
        }
    )
    assert rule_with_name.if_block.name == "MyRule:switchbot"

    # Test with rule name as None
    rule_without_name = AutomationRule.model_validate(
        {
            "if": {"source": "mqtt_timer", "duration": 10, "topic": "test/topic"},
            "then": [{"type": "shell_command", "command": "echo hello"}],
        }
    )
    assert rule_without_name.if_block.name == "Unnamed Rule:mqtt_timer"


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


def test_app_settings_with_multiple_automations():
    config_data = {
        "automations": [
            {
                "if": {"source": "switchbot_timer", "duration": 60},
                "then": [{"type": "webhook", "url": "http://example.com/turn_on"}],
            },
            {
                "if": {"source": "mqtt", "topic": "home/light/status"},
                "then": [
                    {"type": "shell_command", "command": "echo 'Light status changed'"}
                ],
            },
        ]
    }
    settings = AppSettings.model_validate(config_data)
    assert len(settings.automations) == 2
    assert settings.automations[0].if_block.source == "switchbot_timer"
    assert settings.automations[1].if_block.source == "mqtt"
    assert settings.automations[1].if_block.topic == "home/light/status"
    assert isinstance(settings.automations[0].then_block[0], WebhookAction)
    assert isinstance(settings.automations[1].then_block[0], ShellCommandAction)
    assert (
        settings.automations[1].then_block[0].command == "echo 'Light status changed'"
    )
