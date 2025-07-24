import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.signals import state_changed


class TestAutomationHandler:
    @pytest.mark.asyncio
    async def test_init_creates_correct_action_runners(self):
        with (
            patch(
                "switchbot_actions.handlers.EventActionRunner"
            ) as mock_event_action_runner,
            patch(
                "switchbot_actions.handlers.TimerActionRunner"
            ) as mock_timer_action_runner,
        ):
            configs = [
                {"if": {"source": "switchbot"}, "name": "config1"},
                {"if": {"source": "switchbot_timer"}, "name": "config2"},
            ]
            handler = AutomationHandler(configs)

            assert len(handler._action_runners) == 2
            mock_event_action_runner.assert_called_once_with(configs[0])
            mock_timer_action_runner.assert_called_once_with(configs[1])

    @pytest.mark.asyncio
    async def test_init_logs_warning_for_unknown_source(self, caplog):
        configs = [{"if": {"source": "unknown"}, "name": "config3"}]
        with caplog.at_level(logging.WARNING):
            AutomationHandler(configs)
            assert "Unknown source 'unknown' for config" in caplog.text
        assert len(caplog.records) == 1  # Only the warning, no info log for 0 runners

    @pytest.mark.asyncio
    @patch(
        "switchbot_actions.handlers.AutomationHandler._run_all_runners",
        new_callable=AsyncMock,
    )
    async def test_handle_signal_schedules_runner_task(self, mock_run_all_runners):
        configs = [{"if": {"source": "switchbot"}, "name": "config1"}]
        _ = AutomationHandler(configs)

        new_state = MagicMock()
        new_state.address = "DE:AD:BE:EF:00:01"

        state_changed.send(None, new_state=new_state)
        await asyncio.sleep(0)

        mock_run_all_runners.assert_awaited_once_with(new_state)

    @pytest.mark.asyncio
    async def test_handle_signal_does_nothing_if_no_new_state(self):
        configs = [{"if": {"source": "switchbot"}, "name": "config1"}]
        handler = AutomationHandler(configs)

        # Mock the run method of the internal runner to ensure it's not called
        runner_instance = handler._action_runners[0]
        runner_instance.run = AsyncMock()

        handler.handle_signal(sender=None)
        handler.handle_signal(sender=None, new_state=None)
        await asyncio.sleep(0)
        runner_instance.run.assert_not_called()
