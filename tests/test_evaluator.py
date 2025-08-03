import aiomqtt
import pytest

from switchbot_actions.config import AutomationIf
from switchbot_actions.evaluator import StateObject, create_state_object
from switchbot_actions.triggers import EdgeTrigger, _evaluate_single_condition


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
def test_evaluate_single_condition(condition, value, expected):
    """Test various condition evaluations using _evaluate_single_condition."""
    assert _evaluate_single_condition(condition, value) == expected


def test_check_conditions_device_pass(sample_state: StateObject):
    """Test that device conditions pass using Trigger._check_all_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoSensorTH",
        },
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True


def test_check_conditions_device_fail(sample_state: StateObject):
    """Test that device conditions fail using Trigger._check_all_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoPresence",
        },
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_state_pass(sample_state: StateObject):
    """Test that state conditions pass using Trigger._check_all_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={"temperature": "> 20", "humidity": "< 60"},
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True


def test_check_conditions_state_fail(sample_state: StateObject):
    """Test that state conditions fail using Trigger._check_all_conditions."""
    if_config = AutomationIf(source="switchbot", conditions={"temperature": "> 30"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_rssi(sample_state: StateObject):
    """Test that RSSI conditions are checked correctly using
    Trigger._check_all_conditions."""
    if_config = AutomationIf(source="switchbot", conditions={"rssi": "> -60"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True
    if_config = AutomationIf(source="switchbot", conditions={"rssi": "< -60"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_no_data(sample_state: StateObject):
    """Test conditions when a key is not in state data using
    Trigger._check_all_conditions."""
    if_config = AutomationIf(
        source="switchbot", conditions={"non_existent_key": "some_value"}
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is None


def test_check_conditions_mqtt_payload_pass(
    mqtt_message_plain: aiomqtt.Message,
):
    """Test that MQTT payload conditions pass for plain text using
    Trigger._check_all_conditions."""
    state = create_state_object(mqtt_message_plain)
    if_config = AutomationIf(
        source="mqtt", topic="test/topic", conditions={"payload": "ON"}
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(state) is True


def test_check_conditions_mqtt_payload_fail(
    mqtt_message_plain: aiomqtt.Message,
):
    """Test that MQTT payload conditions fail for plain text using
    Trigger._check_all_conditions."""
    state = create_state_object(mqtt_message_plain)
    if_config = AutomationIf(
        source="mqtt", topic="test/topic", conditions={"payload": "OFF"}
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(state) is False


def test_check_conditions_mqtt_json_pass(
    mqtt_message_json: aiomqtt.Message,
):
    """Test that MQTT payload conditions pass for JSON using
    Trigger._check_all_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"temperature": "> 25.0", "humidity": "== 55"},
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(state) is True


def test_check_conditions_mqtt_json_fail(
    mqtt_message_json: aiomqtt.Message,
):
    """Test that MQTT payload conditions fail for JSON using
    Trigger._check_all_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"temperature": "< 25.0"},
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(state) is False


def test_check_conditions_mqtt_json_no_key(
    mqtt_message_json: aiomqtt.Message,
):
    """Test MQTT conditions when a key is not in the JSON payload using
    Trigger._check_all_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"non_existent_key": "some_value"},
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(state) is None


def test_check_conditions_boolean_values(sample_state: StateObject):
    """Test boolean condition evaluation."""
    # Assuming sample_state can be mocked or has a 'power' attribute
    # For this test, we'll temporarily modify the sample_state's internal dict
    # In a real scenario, you'd mock the _get_values_as_dict or use a specific
    # state object
    sample_state._cached_values = {"power": True}
    if_config = AutomationIf(source="switchbot", conditions={"power": "true"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True

    sample_state._cached_values = {"power": False}
    if_config = AutomationIf(source="switchbot", conditions={"power": "false"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True

    sample_state._cached_values = {"power": True}
    if_config = AutomationIf(source="switchbot", conditions={"power": "false"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_string_comparison(sample_state: StateObject):
    """Test string condition evaluation."""
    sample_state._cached_values = {"status": "open"}
    if_config = AutomationIf(source="switchbot", conditions={"status": "== open"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True

    if_config = AutomationIf(source="switchbot", conditions={"status": "!= closed"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True

    if_config = AutomationIf(source="switchbot", conditions={"status": "== closed"})
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_combined_conditions(sample_state: StateObject):
    """Test evaluation of multiple conditions (AND logic)."""
    sample_state._cached_values = {"temperature": 25.0, "humidity": 50, "power": True}
    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "temperature": "> 20",
            "humidity": "< 60",
            "power": "true",
        },
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is True

    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "temperature": "> 30",  # This will fail
            "humidity": "< 60",
            "power": "true",
        },
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False

    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "temperature": "> 20",
            "non_existent_key": "some_value",  # This will result in None
        },
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is None
