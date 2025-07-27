import asyncio
import logging
from unittest.mock import AsyncMock, patch

import aiomqtt
import pytest

from switchbot_actions.config import AutomationRule
from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.mqtt import mqtt_message_received
from switchbot_actions.signals import switchbot_advertisement_received


@pytest.fixture
def mock_mqtt_message() -> aiomqtt.Message:
    """A sample aiomqtt.Message object for testing."""
    message = aiomqtt.Message(
        topic=aiomqtt.Topic("test/topic"),
        payload=b"ON",
        qos=1,
        retain=False,
        mid=1,
        properties=None,
    )
    return message


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
                AutomationRule.model_validate(
                    {
                        "name": "config1",
                        "if": {"source": "switchbot"},
                        "then": [{"type": "shell_command", "command": "echo 'test'"}],
                    }
                ),
                AutomationRule.model_validate(
                    {
                        "name": "config2",
                        "if": {"source": "switchbot_timer", "duration": "3m"},
                        "then": [{"type": "shell_command", "command": "echo 'test'"}],
                    }
                ),
            ]
            handler = AutomationHandler(configs)

            assert len(handler._action_runners) == 2
            mock_event_action_runner.assert_called_once_with(configs[0])
            mock_timer_action_runner.assert_called_once_with(configs[1])

    @pytest.mark.asyncio
    async def test_init_logs_warning_for_unknown_source(self, caplog):
        configs = [
            AutomationRule.model_validate(
                {
                    "name": "config3",
                    "if": {"source": "unknown"},
                    "then": [{"type": "shell_command", "command": "echo 'test'"}],
                }
            )
        ]
        with caplog.at_level(logging.WARNING):
            AutomationHandler(configs)
            assert "Unknown source 'unknown' for config" in caplog.text
        assert len(caplog.records) == 1  # Only the warning, no info log for 0 runners

    @pytest.mark.asyncio
    @patch(
        "switchbot_actions.handlers.AutomationHandler._run_all_runners",
        new_callable=AsyncMock,
    )
    async def test_handle_state_change_schedules_runner_task(
        self, mock_run_all_runners, mock_switchbot_advertisement
    ):
        configs = [
            AutomationRule.model_validate(
                {
                    "name": "config1",
                    "if": {"source": "switchbot"},
                    "then": [{"type": "shell_command", "command": "echo 'test'"}],
                }
            ),
        ]
        _ = AutomationHandler(configs)

        new_state = mock_switchbot_advertisement(address="DE:AD:BE:EF:00:01")

        switchbot_advertisement_received.send(None, new_state=new_state)
        await asyncio.sleep(0)

        mock_run_all_runners.assert_awaited_once_with(new_state)

    @pytest.mark.asyncio
    async def test_handle_state_change_does_nothing_if_no_new_state(self):
        configs = [
            AutomationRule.model_validate(
                {
                    "name": "config1",
                    "if": {"source": "switchbot"},
                    "then": [{"type": "shell_command", "command": "echo 'test'"}],
                }
            ),
        ]
        handler = AutomationHandler(configs)

        # Mock the run method of the internal runner to ensure it's not called
        runner_instance = handler._action_runners[0]
        runner_instance.run = AsyncMock()

        handler.handle_state_change(sender=None)
        handler.handle_state_change(sender=None, new_state=None)
        await asyncio.sleep(0)
        runner_instance.run.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "switchbot_actions.handlers.AutomationHandler._run_all_runners",
        new_callable=AsyncMock,
    )
    async def test_handle_mqtt_message_schedules_runner_task(
        self, mock_run_all_runners, mock_mqtt_message
    ):
        """Test that mqtt_message_received signal triggers the action runner."""
        configs = [
            AutomationRule.model_validate(
                {
                    "name": "mqtt_config",
                    "if": {"source": "mqtt"},
                    "then": [{"type": "shell_command", "command": "echo 'test'"}],
                }
            )
        ]
        _ = AutomationHandler(configs)

        mqtt_message_received.send(None, message=mock_mqtt_message)
        await asyncio.sleep(0)  # Allow the event loop to run the task

        mock_run_all_runners.assert_awaited_once_with(mock_mqtt_message)

    @pytest.mark.asyncio
    async def test_handle_mqtt_message_does_nothing_if_no_message(self):
        """Test that handle_mqtt_message does nothing if no message is provided."""
        configs = [
            AutomationRule.model_validate(
                {
                    "name": "config1",
                    "if": {"source": "mqtt"},
                    "then": [{"type": "shell_command", "command": "echo 'test'"}],
                }
            )
        ]
        handler = AutomationHandler(configs)

        runner_instance = handler._action_runners[0]
        runner_instance.run = AsyncMock()

        handler.handle_mqtt_message(sender=None)
        handler.handle_mqtt_message(sender=None, message=None)
        await asyncio.sleep(0)

        runner_instance.run.assert_not_called()


@pytest.mark.asyncio
async def test_run_all_runners_concurrently(mock_switchbot_advertisement):
    configs = [
        AutomationRule.model_validate(
            {
                "name": "config1",
                "if": {"source": "switchbot"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        ),
        AutomationRule.model_validate(
            {
                "name": "config2",
                "if": {"source": "switchbot"},
                "then": [{"type": "shell_command", "command": "echo 'test'"}],
            }
        ),
    ]
    handler = AutomationHandler(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._action_runners[0].run = mock_run_1
    handler._action_runners[1].run = mock_run_2

    new_state = mock_switchbot_advertisement(address="DE:AD:BE:EF:00:03")
    await handler._run_all_runners(new_state)

    mock_run_1.assert_awaited_once_with(new_state)
    mock_run_2.assert_awaited_once_with(new_state)
