import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.action_runner import ActionRunner
from switchbot_actions.config import AutomationRule
from switchbot_actions.state import create_state_object
from switchbot_actions.triggers import EdgeTrigger


class TestActionRunner:
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
                "then": [{"type": "shell_command", "command": ["echo", "test"]}],
            }
        )
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock()
        trigger = MagicMock(spec=EdgeTrigger)  # Mock the trigger
        runner = ActionRunner(config, executors=[mock_executor], trigger=trigger)

        # Run for device 1, should execute
        await runner.execute_actions(state_object_1)
        mock_executor.execute.assert_called_once_with(state_object_1)
        mock_executor.execute.reset_mock()

        # Run for device 2, should also execute as cooldown is per-device
        await runner.execute_actions(state_object_2)
        mock_executor.execute.assert_called_once_with(state_object_2)
        mock_executor.execute.reset_mock()

        # Run for device 1 again within cooldown, should skip
        await runner.execute_actions(state_object_1)
        mock_executor.execute.assert_not_called()

        # Advance time past cooldown for device 1
        with patch("time.time", return_value=time.time() + 15):
            await runner.execute_actions(state_object_1)
            mock_executor.execute.assert_called_once_with(state_object_1)

    @pytest.mark.asyncio
    async def test_run_calls_trigger_process_state(self, mock_switchbot_advertisement):
        config = AutomationRule.model_validate(
            {
                "name": "Test Rule",
                "if": {"source": "mqtt", "topic": "#"},
                "then": [{"type": "shell_command", "command": ["echo", "test"]}],
            }
        )
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock()
        trigger = MagicMock(spec=EdgeTrigger)  # Mock the trigger
        runner = ActionRunner(config, executors=[mock_executor], trigger=trigger)

        raw_state = mock_switchbot_advertisement(address="test_device")
        state_object = create_state_object(raw_state)

        await runner.run(state_object)
        trigger.process_state.assert_called_once_with(state_object)
