from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationIf as ConditionBlock
from switchbot_actions.state import StateObject
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
    cb.source = "switchbot_timer"
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
            ({"non_existent_attr": "== some_value"}, None),  # Attribute not found
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

        # state.previous is None
        mock_state_object.previous = None
        with patch.object(trigger, "_check_all_conditions") as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_action.assert_not_called()
            mock_check_conditions.assert_not_called()


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
