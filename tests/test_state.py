import aiomqtt
import pytest

from switchbot_actions.config import AutomationIf
from switchbot_actions.state import (
    StateObject,
    create_state_object,
    create_state_object_with_previous,
)
from switchbot_actions.triggers import EdgeTrigger, _evaluate_single_condition


@pytest.fixture
def mock_raw_event(mock_switchbot_advertisement):
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 25.5, "humidity": 50, "battery": 99},
        },
    )


@pytest.fixture
def mock_previous_raw_event(mock_switchbot_advertisement):
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 25.0, "humidity": 49, "battery": 98},
        },
    )


@pytest.fixture
def state_with_previous(mock_raw_event, mock_previous_raw_event):
    return create_state_object_with_previous(mock_raw_event, mock_previous_raw_event)


def test_create_state_object_with_previous(state_with_previous):
    assert state_with_previous.id == "DE:AD:BE:EF:00:01"
    assert state_with_previous.previous is not None
    assert state_with_previous.previous.id == "DE:AD:BE:EF:00:01"
    assert state_with_previous.temperature == 25.5
    assert state_with_previous.previous.temperature == 25.0


def test_create_state_object_with_no_previous(mock_raw_event):
    state_object = create_state_object_with_previous(mock_raw_event, None)
    assert state_object.id == mock_raw_event.address
    assert state_object.previous is None
    assert state_object.temperature == 25.5


def test_state_object_attribute_access(state_with_previous):
    assert state_with_previous.temperature == 25.5
    assert state_with_previous.humidity == 50
    assert state_with_previous.previous.temperature == 25.0
    with pytest.raises(AttributeError):
        _ = state_with_previous.non_existent_attribute


def test_state_object_format_simple(state_with_previous):
    template = "Temp: {temperature}, Hum: {humidity}"
    expected = "Temp: 25.5, Hum: 50"
    assert state_with_previous.format(template) == expected


def test_state_object_format_with_previous(state_with_previous):
    template = "Temp changed from {previous.temperature} to {temperature}."
    expected = "Temp changed from 25.0 to 25.5."
    assert state_with_previous.format(template) == expected


def test_state_object_format_dict(state_with_previous):
    template_dict = {
        "current": "{temperature}",
        "previous": "{previous.temperature}",
    }
    expected_dict = {"current": "25.5", "previous": "25.0"}
    assert state_with_previous.format(template_dict) == expected_dict


def test_state_object_format_invalid_key(state_with_previous):
    with pytest.raises(
        ValueError,
        match=(
            "Placeholder 'invalid_key' could not be resolved. The key name is"
            " likely incorrect."
        ),
    ):
        state_with_previous.format("This is an {invalid_key}.")


def test_state_object_format_typo_previous_attribute(state_with_previous):
    with pytest.raises(
        ValueError,
        match=(
            r"Invalid attribute access in placeholder: 'SwitchBotState' object"
            r" has no attribute 'temprature'"
        ),
    ):
        state_with_previous.format("Temp: {previous.temprature}")


def test_state_object_format_typo_top_level_key(state_with_previous):
    with pytest.raises(
        ValueError,
        match=(
            "Placeholder 'temprature' could not be resolved. The key name is"
            " likely incorrect."
        ),
    ):
        state_with_previous.format("Temp: {temprature}")


def test_state_object_format_method_access_denied(state_with_previous):
    with pytest.raises(
        ValueError,
        match=(
            r"Invalid attribute access in placeholder: method access is not"
            r" allowed: previous.format"
        ),
    ):
        state_with_previous.format("Do not call {previous.format}.")


def test_state_object_format_previous_missing(mock_raw_event):
    state = create_state_object_with_previous(mock_raw_event, None)
    assert state.format("Previous temp: {previous.temperature}") == "Previous temp: "
    assert state.format("Previous hum: {previous.humidity}") == "Previous hum: "
    assert (
        state.format("Previous non_existent: {previous.non_existent}")
        == "Previous non_existent: "
    )


def test_state_object_format_access_previous_object(state_with_previous):
    # Accessing the 'previous' object should work if not followed by an attribute
    # The formatter will call `str()` on the object.
    result = state_with_previous.format("Previous state: {previous}")
    assert result.startswith(
        "Previous state: <switchbot_actions.state.SwitchBotState object"
    )


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
