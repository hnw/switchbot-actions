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
from switchbot_actions.timers import Timer


class TestActionRunnerBase:
    @pytest.mark.asyncio
    @patch("switchbot_actions.action_runner.execute_action")
    async def test_execute_actions_with_cooldown_per_device(
        self, mock_execute_action, mock_switchbot_advertisement
    ):
        state_object_1 = mock_switchbot_advertisement(address="device_1")
        state_object_2 = mock_switchbot_advertisement(address="device_2")
        config = AutomationRule.model_validate(
            {
                "name": "Cooldown Test",
                "cooldown": "10s",
                "if": {"source": "switchbot"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        )
        runner = EventActionRunner(config)

        # Run for device 1, should execute
        await runner._execute_actions(state_object_1)
        mock_execute_action.assert_called_once_with(
            config.then_block[0], state_object_1
        )
        mock_execute_action.reset_mock()

        # Run for device 2, should also execute as cooldown is per-device
        await runner._execute_actions(state_object_2)
        mock_execute_action.assert_called_once_with(
            config.then_block[0], state_object_2
        )
        mock_execute_action.reset_mock()

        # Run for device 1 again within cooldown, should skip
        await runner._execute_actions(state_object_1)
        mock_execute_action.assert_not_called()

        # Advance time past cooldown for device 1
        with patch("time.time", return_value=time.time() + 15):
            await runner._execute_actions(state_object_1)
            mock_execute_action.assert_called_once_with(
                config.then_block[0], state_object_1
            )


class TestEventActionRunner:
    @pytest.mark.asyncio
    @patch.object(ActionRunnerBase, "_execute_actions", new_callable=AsyncMock)
    @patch("switchbot_actions.action_runner.check_conditions")
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
        state_object = mock_switchbot_advertisement(address="test_device")
        runner = EventActionRunner(config)

        # Simulate: False -> True -> True -> None -> False
        mock_check_conditions.side_effect = [False, True, True, None, False]

        # 1. False: No action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert not runner._rule_conditions_met.get("test_device")

        # 2. True (edge): Action executed
        await runner.run(state_object)
        mock_execute_actions.assert_called_once_with(state_object)
        assert runner._rule_conditions_met.get("test_device")
        mock_execute_actions.reset_mock()

        # 3. True (sustained): No action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert runner._rule_conditions_met.get("test_device")

        # 4. None: No change in state, no action
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert runner._rule_conditions_met.get("test_device")

        # 5. False: State becomes false
        await runner.run(state_object)
        mock_execute_actions.assert_not_called()
        assert not runner._rule_conditions_met.get("test_device")


class TestTimerActionRunner:
    @pytest.mark.asyncio
    @patch("switchbot_actions.action_runner.Timer")
    @patch("switchbot_actions.action_runner.check_conditions")
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
        runner = TimerActionRunner(config)
        # Each call to Timer should return a new mock instance
        MockTimer.side_effect = [MagicMock(spec=Timer), MagicMock(spec=Timer)]

        state_1 = mock_switchbot_advertisement(address="device_1")
        state_2 = mock_switchbot_advertisement(address="device_2")

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
    @patch("switchbot_actions.action_runner.check_conditions")
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
        runner = TimerActionRunner(config)
        state = mock_switchbot_advertisement(address="test_device")

        # Set initial state to True
        runner._rule_conditions_met["test_device"] = True
        runner._active_timers["test_device"] = MagicMock(spec=Timer)

        # Simulate check_conditions returning None
        mock_check_conditions.return_value = None
        await runner.run(state)

        # Assert that the timer was not stopped and state did not change
        assert runner._rule_conditions_met.get("test_device")
        assert "test_device" in runner._active_timers
        runner._active_timers["test_device"].stop.assert_not_called()

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
        runner = TimerActionRunner(config)
        state = mock_switchbot_advertisement(address="test_device")
        runner._active_timers["test_device"] = MagicMock(spec=Timer)

        await runner._timer_callback(state)

        mock_execute_actions.assert_called_once_with(state)
        assert "test_device" not in runner._active_timers
