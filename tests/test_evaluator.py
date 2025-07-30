# tests/test_evaluator.py
from unittest.mock import MagicMock

import aiomqtt
import pytest
from switchbot import SwitchBotAdvertisement

from switchbot_actions import evaluator
from switchbot_actions.config import AutomationIf


@pytest.fixture
def sample_state() -> SwitchBotAdvertisement:
    """A sample SwitchBotAdvertisement object for testing."""
    return SwitchBotAdvertisement(
        address="e1:22:33:44:55:66",
        data={
            "data": {"temperature": 25.0, "humidity": 50, "battery": 100},
            "modelName": "WoSensorTH",
        },
        rssi=-50,
        device=MagicMock(),
    )


def test_get_state_key(sample_state):
    """Test that get_state_key returns the MAC address."""
    assert evaluator.get_state_key(sample_state) == "e1:22:33:44:55:66"


def test_get_state_key_mqtt(mqtt_message_plain):
    """Test that get_state_key returns the topic for MQTT messages."""
    assert evaluator.get_state_key(mqtt_message_plain) == "test/topic"


@pytest.mark.parametrize(
    "state_obj, key, expected",
    [
        (
            MagicMock(
                spec=SwitchBotAdvertisement,
                rssi=-50,
                data={"data": {"temperature": 25.0}},
            ),
            "rssi",
            -50,
        ),
        (
            MagicMock(
                spec=SwitchBotAdvertisement,
                rssi=-50,
                data={"data": {"temperature": 25.0}},
            ),
            "temperature",
            25.0,
        ),
        (
            MagicMock(
                spec=SwitchBotAdvertisement,
                rssi=-50,
                data={"data": {"temperature": 25.0}},
            ),
            "non_existent",
            None,
        ),
        (
            MagicMock(
                spec=aiomqtt.Message,
                payload="ON",
            ),
            "payload",
            "ON",
        ),
        (
            MagicMock(
                spec=aiomqtt.Message,
                payload='{"temperature": 25.0}',
            ),
            "temperature",
            25.0,
        ),
        (
            MagicMock(
                spec=aiomqtt.Message,
                payload='{"temperature": 25.0}',
            ),
            "non_existent",
            None,
        ),
    ],
)
def test_get_value_from_state(state_obj, key, expected):
    """Test get_value_from_state function."""
    assert evaluator.get_value_from_state(state_obj, key) == expected


@pytest.mark.parametrize(
    "condition, value, expected",
    [
        ("== 25.0", 25.0, True),
        ("25", 25.0, True),
        ("> 20", 25.0, True),
        ("< 30", 25.0, True),
        ("!= 30", 25.0, True),
        ("true", True, True),
        ("false", False, True),
        ("invalid", 123, False),
    ],
)
def test_evaluate_condition(condition, value, expected):
    """Test various condition evaluations."""
    assert evaluator.evaluate_condition(condition, value) == expected


def test_check_conditions_device_pass(sample_state):
    """Test that device conditions pass."""
    if_config = AutomationIf(
        source="switchbot",
        device={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoSensorTH",
        },
    )
    assert evaluator.check_conditions(if_config, sample_state) is True


def test_check_conditions_device_fail(sample_state):
    """Test that device conditions fail."""
    if_config = AutomationIf(
        source="switchbot",
        device={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoPresence",
        },
    )
    assert evaluator.check_conditions(if_config, sample_state) is False


def test_check_conditions_state_pass(sample_state):
    """Test that state conditions pass."""
    if_config = AutomationIf(
        source="switchbot",
        state={"temperature": "> 20", "humidity": "< 60"},
    )
    assert evaluator.check_conditions(if_config, sample_state) is True


def test_check_conditions_state_fail(sample_state):
    """Test that state conditions fail."""
    if_config = AutomationIf(source="switchbot", state={"temperature": "> 30"})
    assert evaluator.check_conditions(if_config, sample_state) is False


def test_check_conditions_rssi(sample_state):
    """Test that RSSI conditions are checked correctly."""
    if_config = AutomationIf(source="switchbot", state={"rssi": "> -60"})
    assert evaluator.check_conditions(if_config, sample_state) is True
    if_config = AutomationIf(source="switchbot", state={"rssi": "< -60"})
    assert evaluator.check_conditions(if_config, sample_state) is False


def test_check_conditions_no_data(sample_state):
    """Test conditions when a key is not in state data."""
    if_config = AutomationIf(
        source="switchbot", state={"non_existent_key": "some_value"}
    )
    assert evaluator.check_conditions(if_config, sample_state) is None


def test_check_conditions_mqtt_payload_pass(mqtt_message_plain):
    """Test that MQTT payload conditions pass for plain text."""
    if_config = AutomationIf(source="mqtt", topic="test/topic", state={"payload": "ON"})
    assert evaluator.check_conditions(if_config, mqtt_message_plain) is True


def test_check_conditions_mqtt_payload_fail(mqtt_message_plain):
    """Test that MQTT payload conditions fail for plain text."""
    if_config = AutomationIf(
        source="mqtt", topic="test/topic", state={"payload": "OFF"}
    )
    assert evaluator.check_conditions(if_config, mqtt_message_plain) is False


def test_check_conditions_mqtt_json_pass(mqtt_message_json):
    """Test that MQTT payload conditions pass for JSON."""
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        state={"temperature": "> 25.0", "humidity": "== 55"},
    )
    assert evaluator.check_conditions(if_config, mqtt_message_json) is True


def test_check_conditions_mqtt_json_fail(mqtt_message_json):
    """Test that MQTT payload conditions fail for JSON."""
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        state={"temperature": "< 25.0"},
    )
    assert evaluator.check_conditions(if_config, mqtt_message_json) is False


def test_check_conditions_mqtt_json_no_key(mqtt_message_json):
    """Test MQTT conditions when a key is not in the JSON payload."""
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        state={"non_existent_key": "some_value"},
    )
    assert evaluator.check_conditions(if_config, mqtt_message_json) is None


def test_format_string(sample_state):
    """Test that placeholders in a string are replaced with actual data."""
    template = "Temperature: {temperature}°C, RSSI: {rssi}"
    expected = "Temperature: 25.0°C, RSSI: -50"
    assert evaluator.format_string(template, sample_state) == expected


def test_format_string_no_placeholder(sample_state):
    """Test that a string without placeholders remains unchanged."""
    template = "Just a normal string."
    assert evaluator.format_string(template, sample_state) == template


def test_format_string_mqtt_plain(mqtt_message_plain):
    """Test formatting with plain text MQTT message."""
    template = "Topic: {topic}, Payload: {payload}"
    expected = "Topic: test/topic, Payload: ON"
    assert evaluator.format_string(template, mqtt_message_plain) == expected


def test_format_string_mqtt_json(mqtt_message_json):
    """Test formatting with JSON MQTT message."""
    template = "Temp: {temperature}, Hum: {humidity}, Topic: {topic}"
    expected = "Temp: 28.5, Hum: 55, Topic: home/sensor1"
    assert evaluator.format_string(template, mqtt_message_json) == expected


def test_format_string_mqtt_nested_json():
    """Test formatting with nested JSON MQTT message."""
    message = aiomqtt.Message(
        topic=aiomqtt.Topic("home/sensor1"),
        payload=b'{"device": {"name": "sensor1"}, "values": {"temp": 22}}',
        qos=1,
        retain=False,
        mid=1,
        properties=None,
    )
    template = "Device: {device.name}, Temp: {values.temp}"
    expected = "Device: sensor1, Temp: 22"
    assert evaluator.format_string(template, message) == expected
