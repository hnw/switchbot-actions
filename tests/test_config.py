import pytest
from pydantic import ValidationError

from switchbot_actions.config import (
    AppSettings,
    AutomationIf,
    AutomationRule,
    DeviceSettings,  # Added for new tests
    LogAction,
    LoggingSettings,
    MqttPublishAction,
    MqttSettings,
    PrometheusExporterSettings,
    ScannerSettings,
    ShellCommandAction,
    SwitchBotCommandAction,
    WebhookAction,
)


def test_mqtt_settings_defaults():
    settings = MqttSettings()  # pyright:ignore[reportCallIssue]
    assert settings.enabled is False
    assert settings.host == "localhost"
    assert settings.port == 1883
    assert settings.username is None
    assert settings.password is None
    assert settings.reconnect_interval == 10


@pytest.mark.parametrize("port", [0, 65536])
def test_mqtt_settings_invalid_port(port):
    with pytest.raises(ValidationError):
        MqttSettings(host="localhost", port=port)


def test_prometheus_settings_defaults():
    settings = PrometheusExporterSettings()  # pyright:ignore[reportCallIssue]
    assert settings.enabled is False
    assert settings.port == 8000
    assert settings.target == {}


@pytest.mark.parametrize("port", [0, 65536])
def test_prometheus_settings_invalid_port(port):
    with pytest.raises(ValidationError):
        PrometheusExporterSettings(port=port)


def test_scanner_settings_defaults():
    settings = ScannerSettings()
    assert settings.duration == 3
    assert settings.wait == 1
    assert settings.interface == 0


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


def test_log_action_valid_message_and_level():
    action = LogAction(type="log", message="Hello, world!", level="DEBUG")
    assert action.message == "Hello, world!"
    assert action.level == "DEBUG"


def test_log_action_default_level():
    action = LogAction(type="log", message="Default level message")
    assert action.message == "Default level message"
    assert action.level == "INFO"


@pytest.mark.parametrize(
    "level_in, level_out",
    [
        ("debug", "DEBUG"),
        ("info", "INFO"),
        ("warning", "WARNING"),
        ("error", "ERROR"),
        ("critical", "CRITICAL"),
    ],
)
def test_log_action_level_case_insensitivity(level_in, level_out):
    action = LogAction(type="log", message="Test message", level=level_in)
    assert action.level == level_out


def test_log_action_invalid_level():
    with pytest.raises(ValidationError):
        LogAction(type="log", message="Invalid level", level="UNKNOWN")  # type: ignore


def test_automation_if_mqtt_source_requires_topic():
    # Valid case
    AutomationIf(source="mqtt", topic="test/topic")
    AutomationIf(source="mqtt", topic="test/topic", duration=1)  # With duration
    AutomationIf(source="switchbot")  # No topic required

    # Invalid cases
    with pytest.raises(ValidationError, match="'topic' is required for source 'mqtt'"):
        AutomationIf(source="mqtt")
    with pytest.raises(ValidationError, match="'topic' is required for source 'mqtt'"):
        AutomationIf(source="mqtt", duration=1)


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
        MqttPublishAction(
            type="mqtt_publish",
            topic="a/b",
            qos=3,  # pyright:ignore[reportArgumentType]
        )


def test_automation_rule_then_block_single_dict_to_list():
    rule = AutomationRule.model_validate(
        {
            "if": {"source": "switchbot"},
            "then": {"type": "shell_command", "command": ["echo", "hello"]},
        }
    )
    assert isinstance(rule.then_block, list)
    assert len(rule.then_block) == 1
    assert isinstance(rule.then_block[0], ShellCommandAction)
    assert rule.then_block[0].command == ["echo", "hello"]


def test_automation_rule_then_block_already_list():
    rule = AutomationRule.model_validate(
        {
            "if": {"source": "switchbot"},
            "then": [
                {"type": "shell_command", "command": ["echo", "hello"]},
                {"type": "webhook", "url": "http://example.com"},
            ],
        }
    )
    assert isinstance(rule.then_block, list)
    assert len(rule.then_block) == 2
    assert isinstance(rule.then_block[0], ShellCommandAction)
    assert rule.then_block[0].command == ["echo", "hello"]
    assert isinstance(rule.then_block[1], WebhookAction)
    assert rule.then_block[1].url == "http://example.com"


def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.config_path == "config.yaml"
    assert settings.debug is False
    assert isinstance(settings.scanner, ScannerSettings)
    assert isinstance(settings.prometheus, PrometheusExporterSettings)
    assert settings.automations.rules == []
    assert settings.automations.devices == {}
    assert isinstance(settings.logging, LoggingSettings)
    assert isinstance(settings.mqtt, MqttSettings)
    assert settings.mqtt.enabled is False
    assert settings.mqtt.host == "localhost"


def test_app_settings_from_dict():
    config_data = {
        "debug": True,
        "scanner": {"duration": 5, "wait": 15},
        "mqtt": {"host": "test.mqtt.org"},
        "automations": [
            {
                "if": {"source": "switchbot", "duration": 60},
                "then": [{"type": "webhook", "url": "http://example.com/turn_on"}],
            }
        ],
    }
    settings = AppSettings.model_validate(config_data)

    assert settings.debug is True
    assert settings.scanner.duration == 5
    assert settings.scanner.wait == 15
    assert settings.mqtt is not None
    assert settings.mqtt.host == "test.mqtt.org"
    assert len(settings.automations.rules) == 1
    assert settings.automations.rules[0].if_block.source == "switchbot"
    assert settings.automations.rules[0].if_block.duration == 60
    assert isinstance(settings.automations.rules[0].then_block[0], WebhookAction)
    assert (
        str(settings.automations.rules[0].then_block[0].url)
        == "http://example.com/turn_on"
    )


# tests/test_config.py


def test_if_block_name_is_unified_with_rule_name():
    """
    Tests that the if_block's name is correctly and consistently set
    from the parent rule's name after AppSettings validation.
    """
    settings = AppSettings.model_validate(
        {
            "automations": [
                {
                    "name": "MyRule",  # Rule with an explicit name
                    "if": {"source": "switchbot"},
                    "then": [{"type": "shell_command", "command": ["echo", "hello"]}],
                },
                {
                    # Rule with no name, should get a default name
                    "if": {"source": "mqtt", "topic": "test"},
                    "then": [{"type": "shell_command", "command": ["echo", "world"]}],
                },
            ]
        }
    )

    rule_with_name = settings.automations.rules[0]
    assert rule_with_name.name == "MyRule"
    assert rule_with_name.if_block.name == "MyRule"

    rule_without_name = settings.automations.rules[1]
    assert rule_without_name.name == "Automation #1"
    assert rule_without_name.if_block.name == "Automation #1"


def test_app_settings_invalid_config_data():
    invalid_config_data = {
        "logging": {"level": "BAD_LEVEL"},  # Invalid log level
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
                "if": {"source": "switchbot", "duration": 60},
                "then": [{"type": "webhook", "url": "http://example.com/turn_on"}],
            },
            {
                "if": {"source": "mqtt", "topic": "home/light/status"},
                "then": [
                    {
                        "type": "shell_command",
                        "command": ["echo", "'Light status changed'"],
                    }
                ],
            },
        ]
    }
    settings = AppSettings.model_validate(config_data)
    assert len(settings.automations.rules) == 2
    assert settings.automations.rules[0].if_block.source == "switchbot"
    assert settings.automations.rules[1].if_block.source == "mqtt"
    assert settings.automations.rules[1].if_block.topic == "home/light/status"
    assert isinstance(settings.automations.rules[0].then_block[0], WebhookAction)
    assert isinstance(settings.automations.rules[1].then_block[0], ShellCommandAction)
    assert settings.automations.rules[1].then_block[0].command == [
        "echo",
        "'Light status changed'",
    ]


def test_switchbot_command_device_reference_success():
    """Test successful validation with a device reference."""
    config = {
        "devices": {
            "living-curtain": {
                "address": "aa:bb:cc:dd:ee:ff",
                "config": {"password": "pass", "retry_count": 5},
            }
        },
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {
                    "type": "switchbot_command",
                    "device": "living-curtain",
                    "command": "set_position",
                    "params": {"position": 100},
                },
            }
        ],
    }
    settings = AppSettings.model_validate(config)
    action = settings.automations.rules[0].then_block[0]
    assert isinstance(action, SwitchBotCommandAction)
    assert action.address == "AA:BB:CC:DD:EE:FF"  # Changed to expect normalized address
    assert action.config == {"password": "pass", "retry_count": 5}
    assert action.params == {"position": 100}


def test_switchbot_command_self_contained_success():
    """Test successful validation for a self-contained action."""
    config = {
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {
                    "type": "switchbot_command",
                    "address": "11:22:33:44:55:66",
                    "config": {"retry_count": 3},
                    "command": "turn_on",
                },
            }
        ]
    }
    settings = AppSettings.model_validate(config)
    action = settings.automations.rules[0].then_block[0]
    assert isinstance(action, SwitchBotCommandAction)
    assert action.address == "11:22:33:44:55:66"
    assert action.config == {"retry_count": 3}
    assert action.command == "turn_on"


def test_switchbot_command_device_reference_not_found_error():
    """Test that validation fails if the device reference is not found."""
    config = {
        "devices": {},
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {
                    "type": "switchbot_command",
                    "device": "non-existent-device",
                    "command": "press",
                },
            }
        ],
    }
    with pytest.raises(
        ValidationError,
        match="Device 'non-existent-device' not found in devices section.",
    ):
        AppSettings.model_validate(config)


def test_switchbot_command_device_and_address_conflict_error():
    """Test that validation fails if both 'device' and 'address' are provided."""
    config = {
        "devices": {"some-device": {"address": "aa:bb:cc:dd:ee:ff"}},
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {
                    "type": "switchbot_command",
                    "device": "some-device",
                    "address": "11:22:33:44:55:66",
                    "command": "press",
                },
            }
        ],
    }
    with pytest.raises(
        ValidationError, match="'device' and 'address' cannot be used simultaneously."
    ):
        AppSettings.model_validate(config)


def test_switchbot_command_missing_device_and_address_error():
    """Test that validation fails if neither 'device' nor 'address' is provided."""
    config = {
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {"type": "switchbot_command", "command": "press"},
            }
        ]
    }
    with pytest.raises(
        ValidationError, match="Either 'device' or 'address' must be specified."
    ):
        AppSettings.model_validate(config)


def test_switchbot_command_config_merge_logic():
    """Test that device-level and action-level configs are merged correctly."""
    config = {
        "devices": {
            "my-device": {
                "address": "aa:bb:cc:dd:ee:ff",
                "config": {"password": "device-pass", "retry_count": 3},
            }
        },
        "automations": [
            {
                "if": {"source": "switchbot"},
                "then": {
                    "type": "switchbot_command",
                    "device": "my-device",
                    "command": "do_something",
                    "config": {"retry_count": 10, "new_param": "action-param"},
                },
            }
        ],
    }
    settings = AppSettings.model_validate(config)
    action = settings.automations.rules[0].then_block[0]
    assert isinstance(action, SwitchBotCommandAction)
    assert action.config == {
        "password": "device-pass",
        "retry_count": 10,  # Action-level overrides device-level
        "new_param": "action-param",
    }


def test_if_block_device_reference_success():
    """Test successful validation with a device reference in if_block."""
    config = {
        "devices": {
            "my-meter": {
                "address": "11:22:33:44:55:66",
                "config": {"model": "meter"},
            }
        },
        "automations": [
            {
                "if": {
                    "source": "switchbot",
                    "device": "my-meter",
                    "conditions": {"temperature": {"gt": 25}},
                },
                "then": [{"type": "shell_command", "command": ["echo", "hot"]}],
            }
        ],
    }
    settings = AppSettings.model_validate(config)
    if_block = settings.automations.rules[0].if_block
    assert if_block.conditions["address"] == "11:22:33:44:55:66"
    assert if_block.conditions["temperature"] == {"gt": 25}


def test_if_block_device_reference_overwrites_address():
    """Test that device reference in if_block overwrites existing address."""
    config = {
        "devices": {
            "my-meter": {
                "address": "11:22:33:44:55:66",
                "config": {"model": "meter"},
            }
        },
        "automations": [
            {
                "if": {
                    "source": "switchbot",
                    "device": "my-meter",
                    "conditions": {
                        "address": "aa:bb:cc:dd:ee:ff",
                        "temperature": {"gt": 25},
                    },
                },
                "then": [{"type": "shell_command", "command": ["echo", "hot"]}],
            }
        ],
    }
    settings = AppSettings.model_validate(config)
    if_block = settings.automations.rules[0].if_block
    assert (
        if_block.conditions["address"] == "11:22:33:44:55:66"  # Should be overwritten
    )
    assert if_block.conditions["temperature"] == {"gt": 25}


def test_if_block_device_reference_no_impact_on_existing_rules():
    """Test that existing rules without device reference are not affected."""
    config = {
        "automations": [
            {
                "if": {
                    "source": "switchbot",
                    "conditions": {
                        "address": "aa:bb:cc:dd:ee:ff",
                        "temperature": {"gt": 25},
                    },
                },
                "then": [{"type": "shell_command", "command": ["echo", "hot"]}],
            }
        ],
    }
    settings = AppSettings.model_validate(config)
    if_block = settings.automations.rules[0].if_block
    assert if_block.conditions["address"] == "aa:bb:cc:dd:ee:ff"
    assert if_block.conditions["temperature"] == {"gt": 25}
    assert if_block.device is None


# New tests for DeviceSettings address validation and normalization
@pytest.mark.parametrize(
    "input_address, expected_address",
    [
        ("11:22:33:AA:BB:CC", "11:22:33:AA:BB:CC"),
        ("11-22-33-aa-bb-cc", "11:22:33:AA:BB:CC"),
        ("11:22:33:aa:bb:cc", "11:22:33:AA:BB:CC"),
        ("A1:B2:C3:D4:E5:F6", "A1:B2:C3:D4:E5:F6"),
        ("a1-b2-c3-d4-e5-f6", "A1:B2:C3:D4:E5:F6"),
        ("00:00:00:00:00:00", "00:00:00:00:00:00"),
        (
            "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
            "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
        ),
        (
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
        ),
        (
            "12345678-1234-5678-1234-567812345678",
            "12345678-1234-5678-1234-567812345678",
        ),
    ],
)
def test_device_settings_valid_address_normalization(input_address, expected_address):
    settings = DeviceSettings(address=input_address)
    assert settings.address == expected_address


@pytest.mark.parametrize(
    "invalid_address",
    [
        "11:22:33:44:55",  # Too short
        "11:22:33:44:55:66:77",  # Too long
        "11:22:33:44:55:GG",  # Invalid character
        "invalid-mac-address",
        "12345678-1234-5678-1234-56781234567",  # UUID too short
        "12345678-1234-5678-1234-5678123456789",  # UUID too long
        "12345678-1234-5678-1234-56781234567G",  # UUID invalid char
        "",  # Empty string
    ],
)
def test_device_settings_invalid_address_format(invalid_address):
    with pytest.raises(
        ValidationError, match="Address '.*' is not a valid MAC address"
    ):  # Updated regex to match the new error message
        DeviceSettings(address=invalid_address)


# New tests for AutomationSettings device alias name validation
@pytest.mark.parametrize(
    "alias_name",
    [
        "my_device",
        "MyDevice",
        "device-1",
        "日本語デバイス",
        "another_device_alias_with_numbers_123",
    ],
)
def test_automation_settings_valid_device_alias_names(alias_name):
    config_data = {
        "automations": [],
        "devices": {alias_name: {"address": "11:22:33:44:55:66"}},
    }
    # Should not raise ValidationError
    AppSettings.model_validate(config_data)


@pytest.mark.parametrize(
    "invalid_alias_name",
    [
        "my.device",
        "my[device]",
        "my]device",
        "device.with.dot",
        "device[with_bracket]",
        "device]with_bracket",
    ],
)
def test_automation_settings_invalid_device_alias_names(invalid_alias_name):
    config_data = {
        "automations": [],
        "devices": {invalid_alias_name: {"address": "11:22:33:44:55:66"}},
    }
    with pytest.raises(
        ValidationError, match="Device alias '.*' contains invalid characters."
    ):
        AppSettings.model_validate(config_data)


def test_cross_device_condition_alias_valid():
    # Test with a valid cross-device condition where the alias exists
    config_data = {
        "devices": {"my_sensor": {"address": "AA:BB:CC:DD:EE:FF"}},
        "automations": [
            {
                "name": "ValidRule1",
                "if": {
                    "source": "switchbot",
                    "conditions": {"my_sensor.temperature": "> 25"},
                },
                "then": [{"type": "log", "message": "Temp high"}],
            }
        ],
    }
    settings = AppSettings.model_validate(config_data)
    assert (
        settings.automations.rules[0].name == "ValidRule1"
    )  # Ensure validation passes

    # Test with 'previous.attribute' which should always be allowed
    config_data = {
        "automations": [
            {
                "name": "ValidRule2",
                "if": {
                    "source": "switchbot",
                    "conditions": {"previous.humidity": "< 50"},
                },
                "then": [{"type": "log", "message": "Humidity low"}],
            }
        ],
    }
    settings = AppSettings.model_validate(config_data)
    assert (
        settings.automations.rules[0].name == "ValidRule2"
    )  # Ensure validation passes

    # Test with no cross-device conditions
    config_data = {
        "automations": [
            {
                "name": "ValidRule3",
                "if": {"source": "switchbot", "conditions": {"temperature": "> 20"}},
                "then": [{"type": "log", "message": "Simple temp check"}],
            }
        ],
    }
    settings = AppSettings.model_validate(config_data)
    assert (
        settings.automations.rules[0].name == "ValidRule3"
    )  # Ensure validation passes


def test_cross_device_condition_alias_not_found():
    # Test with a cross-device condition where the alias does NOT exist in devices
    config_data = {
        "devices": {
            "another_sensor": {"address": "11:22:33:44:55:66"}
        },  # 'my_sensor' is missing
        "automations": [
            {
                "name": "InvalidRule",
                "if": {
                    "source": "switchbot",
                    "conditions": {"my_sensor.temperature": "> 25"},
                },
                "then": [{"type": "log", "message": "Temp high"}],
            }
        ],
    }
    with pytest.raises(
        ValidationError,
        match=(
            r"In automation rule 'InvalidRule', the condition 'my_sensor.temperature' "
            r"refers to a device alias 'my_sensor' that is not defined in the "
            r"top-level 'devices' section."
        ),
    ):
        AppSettings.model_validate(config_data)

    # Test with multiple rules, one of which has an invalid alias
    config_data = {
        "devices": {"sensor_a": {"address": "AA:BB:CC:DD:EE:FF"}},
        "automations": [
            {
                "name": "FirstValidRule",
                "if": {
                    "source": "switchbot",
                    "conditions": {"sensor_a.temperature": "> 20"},
                },
                "then": [{"type": "log", "message": "Sensor A temp"}],
            },
            {
                "name": "SecondInvalidRule",
                "if": {
                    "source": "switchbot",
                    "conditions": {"sensor_b.humidity": "< 60"},
                },  # sensor_b is missing
                "then": [{"type": "log", "message": "Sensor B humidity"}],
            },
        ],
    }
    with pytest.raises(
        ValidationError,
        match=(
            r"In automation rule 'SecondInvalidRule', the condition "
            r"'sensor_b.humidity' "
            r"refers to a device alias 'sensor_b' that is not defined in the "
            r"top-level 'devices' section."
        ),
    ):
        AppSettings.model_validate(config_data)


def test_cross_device_condition_no_devices_section():
    # Test that validation is skipped if there is no top-level 'devices' section
    config_data = {
        "automations": [
            {
                "name": "RuleWithCondition",
                "if": {
                    "source": "switchbot",
                    "conditions": {"some_alias.value": "== 1"},
                },
                "then": [{"type": "log", "message": "This will fail"}],
            }
        ]
    }
    # This should pass validation because the check is skipped
    settings = AppSettings.model_validate(config_data)
    assert settings.automations.rules[0].name == "RuleWithCondition"


def test_duration_parsing():
    # Test with integer
    assert AutomationIf.model_validate(
        {"source": "switchbot", "duration": 30}
    ).duration == pytest.approx(30.0)

    # Test with float
    assert AutomationIf.model_validate(
        {"source": "switchbot", "duration": 15.5}
    ).duration == pytest.approx(15.5)

    # Test with valid duration string
    assert AutomationIf.model_validate(
        {"source": "switchbot", "duration": "1m 30s"}
    ).duration == pytest.approx(90.0)

    # Test with another valid duration string
    assert AutomationIf.model_validate(
        {"source": "switchbot", "duration": "2h"}
    ).duration == pytest.approx(7200.0)

    # Test with invalid duration string
    with pytest.raises(ValidationError, match="Invalid duration string: invalid"):
        AutomationIf.model_validate({"source": "switchbot", "duration": "invalid"})

    # Test with None
    assert (
        AutomationIf.model_validate({"source": "switchbot", "duration": None}).duration
        is None
    )

    # Test without duration key
    assert AutomationIf.model_validate({"source": "switchbot"}).duration is None


@pytest.mark.parametrize(
    "invalid_source",
    [
        "switchbot_timer",
        "mqtt_timer",
    ],
)
def test_automation_if_rejects_old_timer_suffix_in_source(invalid_source):
    """
    Tests that the old '_timer' suffix in the 'source' field is rejected.
    This confirms that the breaking change is effective and prevents confusion.
    """
    with pytest.raises(ValidationError):
        AutomationIf.model_validate({"source": invalid_source, "topic": "any/topic"})
