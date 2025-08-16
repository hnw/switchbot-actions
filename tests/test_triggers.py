from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationIf as ConditionBlock
from switchbot_actions.state import StateObject, _NullState
from switchbot_actions.triggers import (
    DurationTrigger,
    EdgeTrigger,
)


@pytest.fixture
def mock_state_object():
    state = MagicMock(spec=StateObject)
    state.id = "test_device"
    state.get_values_dict.return_value = {"some_key": "some_value"}
    state.format.side_effect = lambda x: x  # Default to no formatting for simplicity
    state.temperature = 20.0
    state.humidity = 50.0
    state.previous = None
    return state


@pytest.fixture
def mock_action():
    return AsyncMock()


@pytest.fixture
def mock_condition_block():
    cb = MagicMock(spec=ConditionBlock)
    cb.name = "TestRule"
    cb.duration = None  # Default for EdgeTrigger
    cb.source = "switchbot"
    cb.topic = None
    cb.conditions = {"some_key": "== some_value"}
    return cb


@pytest.fixture
def mock_duration_condition_block():
    cb = MagicMock(spec=ConditionBlock)
    cb.name = "DurationTestRule"
    cb.duration = 1.0
    cb.source = "switchbot"
    cb.topic = None
    cb.conditions = {"some_key": "== some_value"}
    return cb


class TestCheckAllConditions:
    @pytest.fixture
    def state_with_previous(self, mock_state_object):
        prev_state = MagicMock(spec=StateObject)
        prev_state.temperature = 25.0
        prev_state.humidity = 45.0
        prev_state.format.side_effect = lambda x: x
        mock_state_object.previous = prev_state
        return mock_state_object

    # 3.1. Test of _check_all_conditions (previous support)
    # 3.1.1. Test of Left-Hand Side (LHS) support
    @pytest.mark.parametrize(
        "conditions, expected_result",
        [
            ({"previous.temperature": "== 25.0"}, True),
            ({"previous.temperature": "!= 25.0"}, False),
            ({"previous.temperature": "> 20.0"}, True),
            ({"previous.temperature": "< 30.0"}, True),
            ({"previous.temperature": ">= 25.0"}, True),
            ({"previous.temperature": "<= 25.0"}, True),
            ({"previous.temperature": "== 99.0"}, False),  # Mismatch
        ],
    )
    def test_check_all_conditions_lhs_previous_exists(
        self, state_with_previous, conditions, expected_result
    ):
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(state_with_previous) == expected_result

    def test_check_all_conditions_lhs_previous_none(self, mock_state_object):
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = {"previous.temperature": "== 25.0"}
        trigger = EdgeTrigger(mock_if_config)
        # previous is None, so it should return False
        assert trigger._check_all_conditions(mock_state_object) is False

    # 3.1.2. Test of Right-Hand Side (RHS) support
    @pytest.mark.parametrize(
        "current_temp, previous_temp, conditions, expected_result",
        [
            (26.0, 25.0, {"temperature": "> {previous.temperature}"}, True),
            (24.0, 25.0, {"temperature": "> {previous.temperature}"}, False),
            (25.0, 25.0, {"temperature": "== {previous.temperature}"}, True),
            (25.0, 26.0, {"temperature": "< {previous.temperature}"}, True),
            (25.0, 24.0, {"temperature": "< {previous.temperature}"}, False),
        ],
    )
    def test_check_all_conditions_rhs_previous_exists(
        self,
        mock_state_object,
        current_temp,
        previous_temp,
        conditions,
        expected_result,
    ):
        mock_state_object.temperature = current_temp
        prev_state = MagicMock(spec=StateObject)
        prev_state.temperature = previous_temp
        prev_state.format.side_effect = lambda x: x
        mock_state_object.previous = prev_state

        # Mock state.format to correctly handle previous.temperature placeholder
        def mock_format(s):
            if "{previous.temperature}" in s:
                return s.replace("{previous.temperature}", str(prev_state.temperature))
            return s

        mock_state_object.format.side_effect = mock_format

        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_object) == expected_result

    def test_check_all_conditions_rhs_previous_none(self, mock_state_object):
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = {"temperature": "> {previous.temperature}"}
        trigger = EdgeTrigger(mock_if_config)
        # previous is None, {previous.temperature} should expand to empty string,
        # making condition false
        # Mock state.format to return empty string for previous.temperature
        mock_state_object.format.side_effect = lambda s: s.replace(
            "{previous.temperature}", ""
        )
        assert trigger._check_all_conditions(mock_state_object) is False

    # 3.1.3. Compound test
    def test_check_all_conditions_compound_previous(self, state_with_previous):
        state_with_previous.temperature = 26.0
        state_with_previous.humidity = 46.0
        state_with_previous.previous.temperature = 25.0
        state_with_previous.previous.humidity = 45.0

        def mock_format(s):
            s = s.replace(
                "{previous.temperature}", str(state_with_previous.previous.temperature)
            )
            s = s.replace(
                "{previous.humidity}", str(state_with_previous.previous.humidity)
            )
            return s

        state_with_previous.format.side_effect = mock_format

        conditions = {
            "previous.temperature": "== 25.0",
            "temperature": "> {previous.temperature}",
            "previous.humidity": "< 50.0",
            "humidity": ">= {previous.humidity}",
        }
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(state_with_previous) is True

        # Test a failing compound condition
        conditions_fail = {
            "previous.temperature": "== 25.0",
            "temperature": "< {previous.temperature}",  # This will fail
        }
        mock_if_config.conditions = conditions_fail
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(state_with_previous) is False

    # 3.1.4. Regression prevention test
    @pytest.mark.parametrize(
        "conditions, expected_result",
        [
            ({"temperature": "== 20.0"}, True),
            ({"temperature": "> 15.0"}, True),
            ({"temperature": "< 25.0"}, True),
            ({"temperature": "!= 21.0"}, True),
            ({"temperature": "== 99.0"}, False),
            ({"humidity": "== 50.0"}, True),
            ({"humidity": "!= 51.0"}, True),
            ({"non_existent_attr": "== some_value"}, False),
        ],
    )
    def test_check_all_conditions_no_previous(
        self, mock_state_object, conditions, expected_result
    ):
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_object) == expected_result


class TestEdgeTrigger:
    # 3.2. Stateless EdgeTrigger tests
    # 3.2.1. Normal case (rising edge)
    @pytest.mark.asyncio
    async def test_process_state_rising_edge(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate False -> True transition
        # state.previous is False, state is True
        mock_state_object.previous = MagicMock(spec=StateObject)
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, False]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_called_once_with(mock_state_object)
            assert (
                mock_check_conditions.call_count == 2
            )  # Called for current and previous state

    # 3.2.2. Semi-normal case (no edge)
    @pytest.mark.asyncio
    async def test_process_state_no_edge_true_true(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate True -> True transition
        mock_state_object.previous = MagicMock(spec=StateObject)
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, True]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_not_called()
            assert mock_check_conditions.call_count == 2

    @pytest.mark.asyncio
    async def test_process_state_no_edge_false_false(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate False -> False transition
        mock_state_object.previous = MagicMock(spec=StateObject)
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[False, False]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_not_called()
            assert mock_check_conditions.call_count == 2

    @pytest.mark.asyncio
    async def test_process_state_falling_edge_true_false(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate True -> False transition (falling edge)
        mock_state_object.previous = MagicMock(spec=StateObject)
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[False, True]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_not_called()
            assert mock_check_conditions.call_count == 2

    # 3.2.3. Initial event test
    @pytest.mark.asyncio
    async def test_process_state_initial_event_no_previous(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate an empty conditions block
        mock_condition_block.conditions = {}

        # state.previous is None
        mock_state_object.previous = None
        with patch.object(
            trigger, "_check_all_conditions", return_value=True
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_called_once_with(mock_state_object)
            # _check_all_conditions is called once for the current state
            mock_check_conditions.assert_called_once_with(mock_state_object)


class TestDurationTrigger:
    @pytest.mark.asyncio
    async def test_process_state_duration_met(
        self, mock_state_object, mock_action, mock_duration_condition_block
    ):
        trigger = DurationTrigger[StateObject](mock_duration_condition_block)
        trigger.on_triggered(mock_action)

        with (
            patch.object(trigger, "_check_all_conditions", return_value=True),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await trigger.process_state(
                mock_state_object
            )  # Conditions met, timer starts

            # Simulate timer completion
            await trigger._timer_callback(mock_state_object)
            mock_action.assert_called_once_with(mock_state_object)
            assert mock_state_object.id not in trigger._active_timers

    @pytest.mark.asyncio
    async def test_process_state_duration_not_met(
        self, mock_state_object, mock_action, mock_duration_condition_block
    ):
        trigger = DurationTrigger[StateObject](mock_duration_condition_block)
        trigger.on_triggered(mock_action)

        with (
            patch.object(trigger, "_check_all_conditions", side_effect=[True, False]),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await trigger.process_state(
                mock_state_object
            )  # Conditions met, timer starts
            assert mock_state_object.id in trigger._active_timers

            await trigger.process_state(
                mock_state_object
            )  # Conditions are no longer met, timer stops.
            mock_action.assert_not_called()
            assert mock_state_object.id not in trigger._active_timers

    @pytest.mark.asyncio
    async def test_process_state_no_conditions_met(
        self, mock_state_object, mock_action, mock_duration_condition_block
    ):
        trigger = DurationTrigger[StateObject](mock_duration_condition_block)
        trigger.on_triggered(mock_action)

        with (
            patch.object(trigger, "_check_all_conditions", return_value=False),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await trigger.process_state(mock_state_object)
            mock_action.assert_not_called()
            assert mock_state_object.id not in trigger._active_timers


# 3.3. Test of _evaluate_single_condition
@pytest.mark.parametrize(
    "condition, new_value, expected",
    [
        # Integer comparisons
        ("== 10", 10, True),
        ("== 10", 11, False),
        ("!= 10", 11, True),
        ("> 5", 10, True),
        ("< 15", 10, True),
        (">= 10", 10, True),
        ("<= 10", 10, True),
        # Float comparisons
        ("== 10.5", 10.5, True),
        ("> 10.0", 10.5, True),
        # String comparisons
        ("== hello", "hello", True),
        ("!= world", "hello", True),
        # Boolean comparisons
        ("== true", True, True),
        ("== false", False, True),
        ("== true", False, False),
        ("!= true", False, True),
        # Implicit ==
        ("10", 10, True),
        ("hello", "hello", True),
        ("true", True, True),
        # Type mismatch
        ("== 10", "hello", False),
        # None value
        ("== 10", None, False),
    ],
)
def test_evaluate_single_condition(condition, new_value, expected):
    from switchbot_actions.triggers import _evaluate_single_condition

    assert _evaluate_single_condition(condition, new_value) == expected


@pytest.fixture
def mock_state_with_snapshot(mock_state_object):
    """A mock state object that has a snapshot of other devices."""
    living_meter_state = MagicMock(spec=StateObject)
    living_meter_state.temperature = 26.0
    living_meter_state.humidity = 40.0
    living_meter_state.format.side_effect = lambda x: x

    empty_state_device = _NullState()

    # Use a simple object to simulate the snapshot, allowing attribute access.
    # This correctly simulates the production environment where snapshot is an object,
    # not a dict, fixing the bug where tests passed while production failed.
    class Snapshot:
        living_meter: StateObject
        empty_device: StateObject
        pass

    snapshot = Snapshot()
    snapshot.living_meter = living_meter_state
    snapshot.empty_device = empty_state_device

    mock_state_object.snapshot = snapshot
    # The triggering device's own state
    mock_state_object.id = "trigger_device"
    mock_state_object.button_pressed = True

    return mock_state_object


class TestCheckAllConditionsWithCrossDeviceState:
    """Tests for _check_all_conditions with cross-device state access."""

    def test_cross_device_condition_success(self, mock_state_with_snapshot):
        """Test a successful condition check using another device's state."""
        conditions = {"living_meter.temperature": "> 25.0"}
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_with_snapshot) is True

    def test_cross_device_condition_failure(self, mock_state_with_snapshot):
        """Test a failing condition check using another device's state."""
        conditions = {"living_meter.temperature": "< 25.0"}
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_with_snapshot) is False

    def test_combined_local_and_cross_device_conditions_success(
        self, mock_state_with_snapshot
    ):
        """Test local and cross-device conditions that should succeed."""
        conditions = {
            "button_pressed": "== true",
            "living_meter.temperature": "> 25.0",
        }
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_with_snapshot) is True

    def test_combined_local_and_cross_device_conditions_failure(
        self, mock_state_with_snapshot
    ):
        """Test a combination of local and cross-device conditions that should fail."""
        conditions = {
            "button_pressed": "== true",
            "living_meter.temperature": "< 25.0",  # This part fails
        }
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)
        assert trigger._check_all_conditions(mock_state_with_snapshot) is False

    def test_undefined_alias_returns_false_and_logs_error(
        self, mock_state_with_snapshot, caplog
    ):
        """Test that an undefined alias in a condition evaluates to False and
        logs an error."""
        conditions = {"non_existent_alias.temperature": "> 20.0"}
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)

        with caplog.at_level("ERROR"):
            result = trigger._check_all_conditions(mock_state_with_snapshot)
            assert result is False
            assert "Rule 'TestRule'" in caplog.text
            assert (
                "Invalid device alias 'non_existent_alias' in condition key "
                "'non_existent_alias.temperature'. Please check your configuration."
                in caplog.text
            )

    def test_undefined_attribute_returns_false_and_logs_error(
        self, mock_state_with_snapshot, caplog
    ):
        """Test that an undefined attribute for a valid alias evaluates to False\
        and logs an error."""
        conditions = {"living_meter.non_existent_attr": "== 123"}
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)

        with caplog.at_level("ERROR"):
            result = trigger._check_all_conditions(mock_state_with_snapshot)
            assert result is False
            assert "Rule 'TestRule'" in caplog.text
            assert (
                "Device does not have attribute 'non_existent_attr' in condition key "
                "'living_meter.non_existent_attr'. Please check your configuration."
                in caplog.text
            )

    def test_alias_with_empty_state_returns_false_and_no_log(
        self, mock_state_with_snapshot, caplog
    ):
        "Test condition on device with no data (_NullState) evaluates to False\
        and produces no log."
        conditions = {"empty_device.temperature": "> 20.0"}
        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule"
        mock_if_config.conditions = conditions
        trigger = EdgeTrigger(mock_if_config)

        with caplog.at_level("ERROR"):
            result = trigger._check_all_conditions(mock_state_with_snapshot)
            assert result is False
            assert not caplog.text  # No log expected


class TestCheckAllConditionsWithDeviceKey:
    """
    Tests for composite conditions involving the 'device' key and cross-device
    state references ('alias.attribute'), as specified in the SOW.
    """

    @pytest.fixture
    def trigger(self, mock_state_with_snapshot):
        """
        Sets up a trigger where the rule is for 'trigger_device' and has
        conditions that reference 'living_meter'.
        """
        # This state is for "trigger_device"
        assert mock_state_with_snapshot.id == "trigger_device"
        assert mock_state_with_snapshot.button_pressed is True
        # The other device "living_meter" has temperature 26.0
        assert mock_state_with_snapshot.snapshot.living_meter.temperature == 26.0

        mock_if_config = MagicMock(spec=ConditionBlock)
        mock_if_config.name = "TestRule with device key"
        # The 'device' key in the config determines which state object
        # triggers the rule.
        # The test setup simulates that this routing has already happened, and we are
        # now inside the trigger's logic.
        mock_if_config.device = "trigger_device"
        return EdgeTrigger(mock_if_config)

    def test_composite_condition_success(self, trigger, mock_state_with_snapshot):
        """
        SOW Success Case: `device:` key matches the triggering device, and the
        `alias.attribute` condition is also met. The rule should evaluate to True.
        """
        trigger._if_config.conditions = {
            "button_pressed": "== true",  # Condition on the triggering device
            "living_meter.temperature": "> 25.0",  # Condition on another device
        }
        assert trigger._check_all_conditions(mock_state_with_snapshot) is True

    def test_composite_condition_failure_cross_device(
        self, trigger, mock_state_with_snapshot
    ):
        """
        SOW Failure Case 1: `device:` key matches, but the `alias.attribute`
        condition is not met. The rule should evaluate to False.
        """
        trigger._if_config.conditions = {
            "button_pressed": "== true",
            "living_meter.temperature": "< 25.0",  # This cross-device condition fails
        }
        assert trigger._check_all_conditions(mock_state_with_snapshot) is False

    def test_composite_condition_failure_trigger_device(
        self, trigger, mock_state_with_snapshot
    ):
        """
        Another failure case: The cross-device condition is met, but the
        triggering device's own condition is not. The rule should evaluate to False.
        """
        trigger._if_config.conditions = {
            "button_pressed": "== false",  # This condition on the trigger device fails
            "living_meter.temperature": "> 25.0",
        }
        assert trigger._check_all_conditions(mock_state_with_snapshot) is False

    # SOW Failure Case 2 (alias.attribute met, but trigger device is wrong)
    # cannot be tested at the `Trigger` level. That logic resides in a higher-level
    # component (e.g., ActionRunner) that is responsible for routing state updates
    # to the correct trigger based on the `device` key. If the device doesn't
    # match, `process_state` would not even be called on this trigger instance.
