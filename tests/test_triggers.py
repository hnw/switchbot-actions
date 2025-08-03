from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationIf as ConditionBlock
from switchbot_actions.evaluator import StateObject
from switchbot_actions.timers import Timer
from switchbot_actions.triggers import DurationTrigger, EdgeTrigger


@pytest.fixture
def mock_state_object():
    state = MagicMock(spec=StateObject)
    state.id = "test_device"
    state.get_values_dict.return_value = {"some_key": "some_value"}
    state.format.return_value = "formatted_value"
    return state


@pytest.fixture
def mock_callback():
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


class TestEdgeTrigger:
    @pytest.mark.asyncio
    async def test_process_state_edge_true(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        # Simulate False -> True transition
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[False, True]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)  # First call: False
            mock_callback.assert_not_called()
            assert not trigger._rule_conditions_met.get(mock_state_object.id)

            await trigger.process_state(mock_state_object)  # Second call: True (edge)
            mock_callback.assert_called_once_with(mock_state_object)
            assert trigger._rule_conditions_met.get(mock_state_object.id)
            mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_process_state_no_edge(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        # Simulate True -> True transition
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, True]
        ) as mock_check_conditions:
            trigger._rule_conditions_met[mock_state_object.id] = (
                True  # Set initial state to True
            )

            await trigger.process_state(mock_state_object)  # First call: True
            mock_callback.assert_not_called()

            await trigger.process_state(
                mock_state_object
            )  # Second call: True (no edge)
            mock_callback.assert_not_called()
            mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_process_state_false_transition(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        # Simulate True -> False transition
        with patch.object(
            trigger, "_check_all_conditions", side_effect=[True, False]
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)  # First call: True (edge)
            mock_callback.assert_called_once_with(mock_state_object)
            mock_callback.reset_mock()
            assert trigger._rule_conditions_met.get(mock_state_object.id)

            await trigger.process_state(mock_state_object)  # Second call: False
            mock_callback.assert_not_called()
            assert not trigger._rule_conditions_met.get(mock_state_object.id)
            mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_process_state_none_conditions(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        trigger = EdgeTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        with patch.object(
            trigger, "_check_all_conditions", return_value=None
        ) as mock_check_conditions:
            await trigger.process_state(mock_state_object)
            mock_callback.assert_not_called()
            assert not trigger._rule_conditions_met.get(mock_state_object.id)
            mock_check_conditions.assert_called_once_with(mock_state_object)


class TestDurationTrigger:
    @pytest.mark.asyncio
    async def test_process_state_start_timer(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        mock_condition_block.duration = "5s"
        trigger = DurationTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        with patch("switchbot_actions.triggers.Timer") as MockTimer:
            mock_timer_instance = MockTimer.return_value
            with patch.object(
                trigger, "_check_all_conditions", side_effect=[False, True]
            ) as mock_check_conditions:
                await trigger.process_state(mock_state_object)  # False
                MockTimer.assert_not_called()

                await trigger.process_state(mock_state_object)  # True (start timer)
                MockTimer.assert_called_once()
                mock_timer_instance.start.assert_called_once()
                assert mock_state_object.id in trigger._active_timers
                assert trigger._rule_conditions_met.get(mock_state_object.id)
                mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_process_state_stop_timer(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        mock_condition_block.duration = "5s"
        trigger = DurationTrigger(mock_condition_block)
        trigger.set_callback(mock_callback)

        with patch("switchbot_actions.triggers.Timer") as MockTimer:
            mock_timer_instance = MockTimer.return_value
            with patch.object(
                trigger, "_check_all_conditions", side_effect=[True, False]
            ) as mock_check_conditions:
                # Simulate timer already running
                trigger._rule_conditions_met[mock_state_object.id] = True
                trigger._active_timers[mock_state_object.id] = mock_timer_instance

                await trigger.process_state(mock_state_object)  # True (no change)
                MockTimer.assert_not_called()

                await trigger.process_state(mock_state_object)  # False (stop timer)
                mock_timer_instance.stop.assert_called_once()
                assert mock_state_object.id not in trigger._active_timers
                assert not trigger._rule_conditions_met.get(mock_state_object.id)
                mock_check_conditions.assert_called_with(mock_state_object)

    @pytest.mark.asyncio
    async def test_timer_callback_execution(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        mock_condition_block.duration = "1s"
        trigger = DurationTrigger(mock_condition_block)
        trigger.set_callback(mock_callback)

        # Manually trigger the callback as if timer expired
        await trigger._timer_callback(mock_state_object)

        mock_callback.assert_called_once_with(mock_state_object)
        assert mock_state_object.id not in trigger._active_timers

    @pytest.mark.asyncio
    async def test_timer_callback_exception_handling(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        mock_condition_block.duration = "1s"
        trigger = DurationTrigger(mock_condition_block)
        trigger.set_callback(mock_callback)

        # Configure the mock callback to raise an exception
        mock_callback.side_effect = Exception("Test exception")

        # Manually trigger the callback as if timer expired
        with pytest.raises(Exception, match="Test exception"):
            await trigger._timer_callback(mock_state_object)

        # Assert that the callback was still called
        mock_callback.assert_called_once_with(mock_state_object)
        # Crucially, assert that the timer was still cleared from _active_timers
        assert mock_state_object.id not in trigger._active_timers

    @pytest.mark.asyncio
    async def test_process_state_none_conditions(
        self, mock_state_object, mock_callback, mock_condition_block
    ):
        mock_condition_block.duration = "5s"
        trigger = DurationTrigger[StateObject](mock_condition_block)
        trigger.set_callback(mock_callback)

        with patch.object(
            trigger, "_check_all_conditions", return_value=None
        ) as mock_check_conditions:
            # Simulate timer already running
            trigger._rule_conditions_met[mock_state_object.id] = True
            trigger._active_timers[mock_state_object.id] = MagicMock(spec=Timer)

            await trigger.process_state(mock_state_object)
            mock_callback.assert_not_called()
            # Ensure timer state is unchanged
            assert trigger._rule_conditions_met.get(mock_state_object.id)
            assert mock_state_object.id in trigger._active_timers
            mock_check_conditions.assert_called_once_with(mock_state_object)
