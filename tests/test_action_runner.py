import time
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.action_runner import (
    ActionRunnerBase,
    EventActionRunner,
    TimerActionRunner,
)
from switchbot_actions.config import AutomationRule
from switchbot_actions.evaluator import StateObject, create_state_object
from switchbot_actions.timers import Timer


class TestActionRunnerBase:
    @pytest.mark.asyncio
    async def test_execute_actions_with_cooldown_per_device(
        self, mock_switchbot_advertisement
    ):
        raw_state_1 = mock_switchbot_advertisement(address="device_1")
        state_object_1 = create_state_object(raw_state_1)
        raw_state_2 = mock_switchbot_advertisement(address="device_2")
        state_object_2 = create_state_object(raw_state_2)

        config = AutomationRule.model_validate(
            {
                "name": "Cooldown Test",
                "cooldown": "10s",
                "if": {"source": "switchbot"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock()
        runner = EventActionRunner(config, executors=[mock_executor])

        # Run for device 1, should execute
        await runner._execute_actions(state_object_1)
        mock_executor.execute.assert_called_once_with(state_object_1)
        mock_executor.execute.reset_mock()

        # Run for device 2, should also execute as cooldown is per-device
        await runner._execute_actions(state_object_2)
        mock_executor.execute.assert_called_once_with(state_object_2)
        mock_executor.execute.reset_mock()

        # Run for device 1 again within cooldown, should skip
        await runner._execute_actions(state_object_1)
        mock_executor.execute.assert_not_called()

        # Advance time past cooldown for device 1
        with patch("time.time", return_value=time.time() + 15):
            await runner._execute_actions(state_object_1)
            mock_executor.execute.assert_called_once_with(state_object_1)


class TestEventActionRunner:
    @pytest.mark.asyncio
    @patch.object(ActionRunnerBase, "_execute_actions", new_callable=AsyncMock)
    @patch.object(StateObject, "check_conditions")
    async def test_run_executes_actions_on_edge_trigger(
        self, mock_check_conditions, mock_execute_actions, mock_switchbot_advertisement
    ):
        config = AutomationRule.model_validate(
            {
                "name": "Test Rule",
                "if": {"source": "mqtt", "topic": "#"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        raw_state = mock_switchbot_advertisement(address="test_device")
        state_object = create_state_object(raw_state)
        runner = EventActionRunner(config, executors=[])

        # Simulate: False -> True -> True -> None -> False
        mock_check_conditions.side_effect = [False, True, True, None, False]

        # 1. False: No action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert not runner._rule_conditions_met.get(state_object.id)
        await runner.run(state_object)
        mock_execute_actions.assert_called_once_with(state_object)
        assert runner._rule_conditions_met.get(state_object.id)
        mock_execute_actions.reset_mock()

        # 3. True (sustained): No action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert runner._rule_conditions_met.get(state_object.id)

        # 4. None: No change in state, no action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert runner._rule_conditions_met.get(state_object.id)

        # 5. False: State becomes false
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert not runner._rule_conditions_met.get(state_object.id)


class TestTimerActionRunner:
    @pytest.mark.asyncio
    @patch("switchbot_actions.action_runner.Timer")
    @patch.object(StateObject, "check_conditions")
    async def test_timer_logic_per_device(
        self,
        mock_check_conditions: MagicMock,
        MockTimer: MagicMock,
        mock_switchbot_advertisement,
    ):
        config = AutomationRule.model_validate(
            {
                "name": "Timer Test",
                "if": {"source": "mqtt_timer", "duration": "5s", "topic": "#"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        runner = TimerActionRunner(config, executors=[])
        # Each call to Timer should return a new mock instance
        MockTimer.side_effect = [MagicMock(spec=Timer), MagicMock(spec=Timer)]

        raw_state_1 = mock_switchbot_advertisement(address="device_1")
        state_1 = create_state_object(raw_state_1)
        raw_state_2 = mock_switchbot_advertisement(address="device_2")
        state_2 = create_state_object(raw_state_2)

        # Device 1: conditions become true -> start timer
        mock_check_conditions.return_value = True
        await runner.run(state_1)
        assert MockTimer.call_count == 1
        timer1_mock = cast(MagicMock, runner._active_timers["device_1"])
        timer1_mock.start.assert_called_once()
        assert runner._rule_conditions_met.get("device_1")

        # Device 2: conditions become true -> start another timer
        await runner.run(state_2)
        assert MockTimer.call_count == 2
        timer2_mock = cast(MagicMock, runner._active_timers["device_2"])
        timer2_mock.start.assert_called_once()
        assert runner._rule_conditions_met.get("device_2")
        assert timer1_mock != timer2_mock

        # Device 1: conditions become false -> stop timer 1
        mock_check_conditions.return_value = False
        await runner.run(state_1)
        timer1_mock.stop.assert_called_once()
        assert "device_1" not in runner._active_timers
        assert not runner._rule_conditions_met.get("device_1")
        assert "device_2" in runner._active_timers  # Timer 2 should still be active

    @pytest.mark.asyncio
    @patch.object(StateObject, "check_conditions")
    async def test_run_handles_none_from_check_conditions(
        self, mock_check_conditions, caplog, mock_switchbot_advertisement
    ):
        config = AutomationRule.model_validate(
            {
                "name": "Timer Test",
                "if": {"source": "switchbot_timer", "duration": "5s"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        runner = TimerActionRunner(config, executors=[])
        raw_state = mock_switchbot_advertisement(address="test_device")
        state = create_state_object(raw_state)

        # Set initial state to True
        runner._rule_conditions_met["test_device"] = True
        runner._active_timers["test_device"] = MagicMock(spec=Timer)

        # Simulate check_conditions returning None
        mock_check_conditions.return_value = None
        await runner.run(state)

        # Assert that the timer was not stopped and state did not change
        # Assert that the timer was not stopped and state did not change
        assert runner._rule_conditions_met.get(state.id)

    @pytest.mark.asyncio
    @patch.object(TimerActionRunner, "_execute_actions", new_callable=AsyncMock)
    async def test_timer_callback_executes_actions_and_clears_timer(
        self, mock_execute_actions, mock_switchbot_advertisement
    ):
        config = AutomationRule.model_validate(
            {
                "name": "Callback Test",
                "if": {"source": "mqtt_timer", "duration": "1s", "topic": "#"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        runner = TimerActionRunner(config, executors=[])
        raw_state = mock_switchbot_advertisement(address="test_device")
        state = create_state_object(raw_state)
        runner._active_timers["test_device"] = MagicMock(spec=Timer)

        await runner._timer_callback(state)

        mock_execute_actions.assert_called_once_with(state)
        assert "test_device" not in runner._active_timers
