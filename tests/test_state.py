from unittest.mock import MagicMock, patch

import aiomqtt
import pytest

from switchbot_actions.config import AutomationIf, DeviceSettings
from switchbot_actions.state import (
    StateObject,
    StateSnapshot,
    _NullState,
    create_state_object,
)
from switchbot_actions.triggers import EdgeTrigger, _evaluate_single_condition


@pytest.fixture
def mock_raw_event(mock_switchbot_advertisement):
    """Trigger device's event."""
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 25.5, "humidity": 50, "battery": 99},
        },
    )


@pytest.fixture
def mock_previous_raw_event(mock_switchbot_advertisement):
    """Trigger device's previous event."""
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 25.0, "humidity": 49, "battery": 98},
        },
    )


@pytest.fixture
def devices_config() -> dict[str, DeviceSettings]:
    """Fixture for device configurations with aliases."""
    return {
        "living_meter": DeviceSettings.model_validate({"address": "AA:BB:CC:DD:EE:FF"}),
        "bedroom_meter": DeviceSettings.model_validate(
            {"address": "11:22:33:44:55:66"}
        ),
        "unseen_meter": DeviceSettings.model_validate({"address": "66:77:88:99:AA:BB"}),
        # This alias has the same name as a key in the trigger device's data
        "temperature": DeviceSettings.model_validate({"address": "FF:FF:FF:FF:FF:FF"}),
    }


@pytest.fixture
def raw_events(mock_switchbot_advertisement) -> dict[str, MagicMock]:
    """Fixture for a dictionary of raw events from multiple devices."""
    return {
        "AA:BB:CC:DD:EE:FF": mock_switchbot_advertisement(
            address="AA:BB:CC:DD:EE:FF",
            data={
                "modelName": "WoSensorTH",
                "data": {"temperature": 22.0, "humidity": 45, "battery": 90},
            },
        ),
        # Note: No event for bedroom_meter (11:22:33:44:55:66)
        "FF:FF:FF:FF:FF:FF": mock_switchbot_advertisement(
            address="FF:FF:FF:FF:FF:FF",
            data={
                "modelName": "WoSensorTH",
                "data": {"temperature": 18.0, "humidity": 60, "battery": 80},
            },
        ),
    }


@pytest.fixture
def snapshot(raw_events, devices_config) -> StateSnapshot:
    """Fixture for a StateSnapshot instance."""
    return StateSnapshot(raw_events=raw_events, devices_config=devices_config)


class TestStateSnapshot:
    @patch("switchbot_actions.state.create_state_object")
    def test_getattr_lazy_loads_and_caches_state_object(
        self, mock_create, snapshot, raw_events, devices_config
    ):
        """Test that getattr lazy-loads a StateObject and caches it."""
        # First access: should create a new object
        snapshot.living_meter
        mock_create.assert_called_once_with(
            raw_events[devices_config["living_meter"].address],
            previous=None,
            snapshot=snapshot,
        )

        # Second access: should not create a new object
        mock_create.reset_mock()
        snapshot.living_meter
        mock_create.assert_not_called()

    def test_getattr_raises_attribute_error_for_unknown_alias(self, snapshot):
        """Test that accessing an unconfigured alias raises an AttributeError."""
        with pytest.raises(
            AttributeError,
            match="^'StateSnapshot' object has no attribute 'unknown_device'$",
        ):
            _ = snapshot.unknown_device

    def test_getattr_returns_empty_state_for_missing_raw_event(self, snapshot):
        """Test that accessing a configured alias with no event returns EmptyState."""
        result = snapshot.bedroom_meter
        assert isinstance(result, _NullState)


class TestStateObjectFormatting:
    def test_format_cross_device_access(self, mock_raw_event, snapshot):
        """Test formatting with placeholders for other devices."""
        state_object = create_state_object(mock_raw_event, snapshot=snapshot)
        template = (
            "Trigger temp: {temperature}, Living temp: {living_meter.temperature}."
        )
        expected = "Trigger temp: 25.5, Living temp: 22.0."
        assert state_object.format(template) == expected

    def test_format_name_resolution_priority(
        self, mock_raw_event, mock_previous_raw_event, snapshot
    ):
        """Test that placeholder resolution follows the specified priority."""
        previous_state = create_state_object(mock_previous_raw_event, snapshot=snapshot)
        state_object = create_state_object(
            mock_raw_event, previous=previous_state, snapshot=snapshot
        )

        # 1. 'previous' keyword has top priority
        template = "Temp changed from {previous.temperature}."
        assert state_object.format(template) == "Temp changed from 25.0."

        # 2. Trigger's own key is preferred over a device alias with the same name
        template = "Current temperature is {temperature}."
        assert state_object.format(template) == "Current temperature is 25.5."

        # 3. Device alias is used when no other key matches
        template = "Living room humidity is {living_meter.humidity}."
        assert state_object.format(template) == "Living room humidity is 45."

    def test_format_raises_value_error_for_non_existent_device_or_attribute(
        self, mock_raw_event, snapshot
    ):
        """Test that accessing non-existent devices or attributes
        raises a ValueError."""
        state_object = create_state_object(mock_raw_event, snapshot=snapshot)

        # Access a valid attribute of a non-existent device
        template = "{non_existent_device.temperature}"
        with pytest.raises(
            ValueError,
            match=(
                "^Placeholder 'non_existent_device' could not be resolved. "
                "The key name is likely incorrect.$"
            ),
        ):
            state_object.format(template)

        # Access a non-existent attribute of a valid device
        template = "{living_meter.non_existent_attribute}"
        with pytest.raises(
            ValueError,
            match=(
                "^Invalid attribute access in placeholder: 'SwitchBotState' "
                "object has no attribute 'non_existent_attribute'$"
            ),
        ):
            state_object.format(template)

        # Test accessing a configured device for which no data is yet available.
        template = "{unseen_meter.temperature}"
        # This case should return an empty string due to _NullState's behavior
        assert state_object.format(template) == ""


def test_state_object_attribute_access(mock_raw_event, mock_previous_raw_event):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    assert state_object.temperature == 25.5
    assert state_object.humidity == 50
    assert state_object.previous.temperature == 25.0
    with pytest.raises(AttributeError):
        _ = state_object.non_existent_attribute


def test_create_state_object_with_previous_argument(
    mock_raw_event, mock_previous_raw_event
):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)

    assert state_object.id == mock_raw_event.address
    assert state_object.previous is not None
    assert state_object.previous.id == mock_previous_raw_event.address
    assert state_object.temperature == 25.5
    assert state_object.previous.temperature == 25.0


def test_state_object_format_simple(mock_raw_event, mock_previous_raw_event):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    template = "Temp: {temperature}, Hum: {humidity}"
    expected = "Temp: 25.5, Hum: 50"
    assert state_object.format(template) == expected


def test_state_object_format_with_previous(mock_raw_event, mock_previous_raw_event):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    template = "Temp changed from {previous.temperature} to {temperature}."
    expected = "Temp changed from 25.0 to 25.5."
    assert state_object.format(template) == expected


def test_state_object_format_dict(mock_raw_event, mock_previous_raw_event):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    template_dict = {
        "current": "{temperature}",
        "previous": "{previous.temperature}",
    }
    expected_dict = {"current": "25.5", "previous": "25.0"}
    assert state_object.format(template_dict) == expected_dict


def test_state_object_format_invalid_key(mock_raw_event, mock_previous_raw_event):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    with pytest.raises(
        ValueError,
        match=(
            "Placeholder 'invalid_key' could not be resolved. The key name is"
            " likely incorrect."
        ),
    ):
        state_object.format("This is an {invalid_key}.")


def test_state_object_format_typo_previous_attribute(
    mock_raw_event, mock_previous_raw_event
):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    with pytest.raises(
        ValueError,
        match=(
            r"Invalid attribute access in placeholder: 'SwitchBotState' object"
            r" has no attribute 'temprature'"
        ),
    ):
        state_object.format("Temp: {previous.temprature}")


def test_state_object_format_typo_top_level_key(
    mock_raw_event, mock_previous_raw_event
):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    with pytest.raises(
        ValueError,
        match=(
            "Placeholder 'temprature' could not be resolved. The key name is"
            " likely incorrect."
        ),
    ):
        state_object.format("Temp: {temprature}")


def test_state_object_format_method_access_denied(
    mock_raw_event, mock_previous_raw_event
):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    with pytest.raises(
        ValueError,
        match=(
            r"Invalid attribute access in placeholder: method access is not"
            r" allowed: previous.format"
        ),
    ):
        state_object.format("Do not call {previous.format}.")


def test_state_object_format_previous_missing(mock_raw_event):
    state = create_state_object(mock_raw_event, previous=None)
    assert state.format("Previous temp: {previous.temperature}") == "Previous temp: "
    assert state.format("Previous hum: {previous.humidity}") == "Previous hum: "
    assert (
        state.format("Previous non_existent: {previous.non_existent}")
        == "Previous non_existent: "
    )


def test_state_object_format_access_previous_object(
    mock_raw_event, mock_previous_raw_event
):
    previous_state_object = create_state_object(mock_previous_raw_event)
    state_object = create_state_object(mock_raw_event, previous=previous_state_object)
    # Accessing the 'previous' object should work if not followed by an attribute
    # The formatter will call `str()` on the object.
    result = state_object.format("Previous state: {previous}")
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
    assert trigger._check_all_conditions(sample_state) is False


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
    assert trigger._check_all_conditions(state) is False


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
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_invalid_operator(sample_state: StateObject):
    """Test that an invalid operator returns False."""
    sample_state._cached_values = {"temperature": 25.0}
    if_config = AutomationIf(
        source="switchbot", conditions={"temperature": "invalid_op 20"}
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False


def test_check_conditions_invalid_value_type(sample_state: StateObject):
    """Test that a condition with a non-comparable value returns False."""
    sample_state._cached_values = {"temperature": 25.0}
    if_config = AutomationIf(
        source="switchbot", conditions={"temperature": "> non_numeric_value"}
    )
    trigger = EdgeTrigger(if_config)
    assert trigger._check_all_conditions(sample_state) is False
