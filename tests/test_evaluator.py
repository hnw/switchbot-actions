import aiomqtt
import pytest

from switchbot_actions.config import AutomationIf
from switchbot_actions.evaluator import StateObject, create_state_object


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
def test_state_object_evaluate_condition(
    sample_state: StateObject, condition, value, expected
):
    """Test various condition evaluations using StateObject._evaluate_condition."""
    assert sample_state._evaluate_condition(condition, value) == expected


def test_state_object_check_conditions_device_pass(sample_state: StateObject):
    """Test that device conditions pass using StateObject.check_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoSensorTH",
        },
    )
    assert sample_state.check_conditions(if_config) is True


def test_state_object_check_conditions_device_fail(sample_state: StateObject):
    """Test that device conditions fail using StateObject.check_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "address": "e1:22:33:44:55:66",
            "modelName": "WoPresence",
        },
    )
    assert sample_state.check_conditions(if_config) is False


def test_state_object_check_conditions_state_pass(sample_state: StateObject):
    """Test that state conditions pass using StateObject.check_conditions."""
    if_config = AutomationIf(
        source="switchbot",
        conditions={"temperature": "> 20", "humidity": "< 60"},
    )
    assert sample_state.check_conditions(if_config) is True


def test_state_object_check_conditions_state_fail(sample_state: StateObject):
    """Test that state conditions fail using StateObject.check_conditions."""
    if_config = AutomationIf(source="switchbot", conditions={"temperature": "> 30"})
    assert sample_state.check_conditions(if_config) is False


def test_state_object_check_conditions_rssi(sample_state: StateObject):
    """Test that RSSI conditions are checked correctly using
    StateObject.check_conditions."""
    if_config = AutomationIf(source="switchbot", conditions={"rssi": "> -60"})
    assert sample_state.check_conditions(if_config) is True
    if_config = AutomationIf(source="switchbot", conditions={"rssi": "< -60"})
    assert sample_state.check_conditions(if_config) is False


def test_state_object_check_conditions_no_data(sample_state: StateObject):
    """Test conditions when a key is not in state data using
    StateObject.check_conditions."""
    if_config = AutomationIf(
        source="switchbot", conditions={"non_existent_key": "some_value"}
    )
    assert sample_state.check_conditions(if_config) is None


def test_state_object_check_conditions_mqtt_payload_pass(
    mqtt_message_plain: aiomqtt.Message,
):
    """Test that MQTT payload conditions pass for plain text using
    StateObject.check_conditions."""
    state = create_state_object(mqtt_message_plain)
    if_config = AutomationIf(
        source="mqtt", topic="test/topic", conditions={"payload": "ON"}
    )
    assert state.check_conditions(if_config) is True


def test_state_object_check_conditions_mqtt_payload_fail(
    mqtt_message_plain: aiomqtt.Message,
):
    """Test that MQTT payload conditions fail for plain text using
    StateObject.check_conditions."""
    state = create_state_object(mqtt_message_plain)
    if_config = AutomationIf(
        source="mqtt", topic="test/topic", conditions={"payload": "OFF"}
    )
    assert state.check_conditions(if_config) is False


def test_state_object_check_conditions_mqtt_json_pass(
    mqtt_message_json: aiomqtt.Message,
):
    """Test that MQTT payload conditions pass for JSON using
    StateObject.check_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"temperature": "> 25.0", "humidity": "== 55"},
    )
    assert state.check_conditions(if_config) is True


def test_state_object_check_conditions_mqtt_json_fail(
    mqtt_message_json: aiomqtt.Message,
):
    """Test that MQTT payload conditions fail for JSON using
    StateObject.check_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"temperature": "< 25.0"},
    )
    assert state.check_conditions(if_config) is False


def test_state_object_check_conditions_mqtt_json_no_key(
    mqtt_message_json: aiomqtt.Message,
):
    """Test MQTT conditions when a key is not in the JSON payload using
    StateObject.check_conditions."""
    state = create_state_object(mqtt_message_json)
    if_config = AutomationIf(
        source="mqtt",
        topic="home/sensor1",
        conditions={"non_existent_key": "some_value"},
    )
    assert state.check_conditions(if_config) is None


def test_state_object_check_conditions_boolean_values(sample_state: StateObject):
    """Test boolean condition evaluation."""
    # Assuming sample_state can be mocked or has a 'power' attribute
    # For this test, we'll temporarily modify the sample_state's internal dict
    # In a real scenario, you'd mock the _get_values_as_dict or use a specific
    # state object
    sample_state._cached_values = {"power": True}
    if_config = AutomationIf(source="switchbot", conditions={"power": "true"})
    assert sample_state.check_conditions(if_config) is True

    sample_state._cached_values = {"power": False}
    if_config = AutomationIf(source="switchbot", conditions={"power": "false"})
    assert sample_state.check_conditions(if_config) is True

    sample_state._cached_values = {"power": True}
    if_config = AutomationIf(source="switchbot", conditions={"power": "false"})
    assert sample_state.check_conditions(if_config) is False


def test_state_object_check_conditions_string_comparison(sample_state: StateObject):
    """Test string condition evaluation."""
    sample_state._cached_values = {"status": "open"}
    if_config = AutomationIf(source="switchbot", conditions={"status": "== open"})
    assert sample_state.check_conditions(if_config) is True

    if_config = AutomationIf(source="switchbot", conditions={"status": "!= closed"})
    assert sample_state.check_conditions(if_config) is True

    if_config = AutomationIf(source="switchbot", conditions={"status": "== closed"})
    assert sample_state.check_conditions(if_config) is False


def test_state_object_check_conditions_combined_conditions(sample_state: StateObject):
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
    assert sample_state.check_conditions(if_config) is True

    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "temperature": "> 30",  # This will fail
            "humidity": "< 60",
            "power": "true",
        },
    )
    assert sample_state.check_conditions(if_config) is False

    if_config = AutomationIf(
        source="switchbot",
        conditions={
            "temperature": "> 20",
            "non_existent_key": "some_value",  # This will result in None
        },
    )
    assert sample_state.check_conditions(if_config) is None
