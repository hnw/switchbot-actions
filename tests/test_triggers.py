from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationIf as ConditionBlock
from switchbot_actions.state import StateObject
from switchbot_actions.triggers import DurationTrigger, EdgeTrigger


@pytest.fixture
def mock_state_object():
    state = MagicMock(spec=StateObject)
    state.id = "test_device"
    state.get_values_dict.return_value = {"some_key": "some_value"}
    state.format.return_value = "formatted_value"
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


class TestEdgeTrigger:
    @pytest.mark.asyncio
    async def test_process_state_edge_true(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate False -> True transition
        with patch.object(trigger, "_check_all_conditions", side_effect=[False, True]):
            await trigger.process_state(mock_state_object)  # First call: False
            mock_action.assert_not_called()

            await trigger.process_state(mock_state_object)  # Second call: True (edge)
            mock_action.assert_called_once_with(mock_state_object)
            assert trigger._rule_conditions_met.get(mock_state_object.id)

    @pytest.mark.asyncio
    async def test_process_state_no_edge_true(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate True -> True transition
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, True]
        ) as mock_check_conditions:
            trigger._rule_conditions_met[mock_state_object.id] = (
                True  # Set initial state to True
            )

            await trigger.process_state(mock_state_object)  # First call: True
            mock_action.assert_not_called()

            await trigger.process_state(
                mock_state_object
            )  # Second call: True (no edge)
            mock_action.assert_not_called()
            mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_process_state_false_transition(
        self, mock_state_object, mock_action, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.on_triggered(mock_action)

        # Simulate True -> False transition
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, False]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)  # First call: True (edge)
            mock_action.assert_called_once_with(mock_state_object)
            mock_action.reset_mock()
            assert trigger._rule_conditions_met.get(mock_state_object.id)

            await trigger.process_state(mock_state_object)  # Second call: False
            mock_action.assert_not_called()
            assert not trigger._rule_conditions_met.get(mock_state_object.id)
            mock_check_conditions.assert_called_with(mock_state_object)


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
            )  # Conditions no longer met, timer stops
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
