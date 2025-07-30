# tests/test_handlers.py
import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from switchbot_actions.config import AutomationRule
from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.mqtt import mqtt_message_received
from switchbot_actions.signals import switchbot_advertisement_received

# --- Fixtures ---


@pytest.fixture
def automation_handler_factory():
    """
    A factory fixture to create isolated AutomationHandler instances for each test.
    Ensures that signal connections are torn down after each test.
    """
    created_handlers = []

    def factory(configs: list[AutomationRule]) -> AutomationHandler:
        handler = AutomationHandler(configs=configs)
        created_handlers.append(handler)
        return handler

    yield factory

    # Teardown: Disconnect all created handlers from signals after the test runs
    for handler in created_handlers:
        switchbot_advertisement_received.disconnect(handler.handle_state_change)
        mqtt_message_received.disconnect(handler.handle_mqtt_message)


# --- Tests ---


def test_init_creates_correct_action_runners(automation_handler_factory):
    """
    Test that the handler initializes the correct type of runners based on config.
    """
    with (
        patch("switchbot_actions.handlers.EventActionRunner") as mock_event,
        patch("switchbot_actions.handlers.TimerActionRunner") as mock_timer,
    ):
        configs = [
            AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
            AutomationRule.model_validate(
                {"if": {"source": "switchbot_timer", "duration": "1s"}, "then": []}
            ),
        ]

        handler = automation_handler_factory(configs)

        assert len(handler._action_runners) == 2
        mock_event.assert_called_once_with(configs[0])
        mock_timer.assert_called_once_with(configs[1])


@pytest.mark.asyncio
@patch(
    "switchbot_actions.handlers.AutomationHandler._run_all_runners",
    new_callable=AsyncMock,
)
@patch("switchbot_actions.handlers.asyncio.create_task")
async def test_handle_state_change_schedules_runner_task(
    mock_create_task,
    mock_run_all_runners,
    automation_handler_factory,
    mock_switchbot_advertisement,
):
    """
    Test that a 'switchbot' signal correctly schedules the runners.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []})
    ]
    _ = automation_handler_factory(configs)

    new_state = mock_switchbot_advertisement()
    switchbot_advertisement_received.send(None, new_state=new_state)

    mock_create_task.assert_called_once()

    coro = mock_create_task.call_args[0][0]
    await coro

    mock_run_all_runners.assert_called_once_with(new_state)


@pytest.mark.asyncio
@patch(
    "switchbot_actions.handlers.AutomationHandler._run_all_runners",
    new_callable=AsyncMock,
)
@patch("switchbot_actions.handlers.asyncio.create_task")
async def test_handle_mqtt_message_schedules_runner_task(
    mock_create_task,
    mock_run_all_runners,
    automation_handler_factory,
    mqtt_message_plain,
):
    """
    Test that an 'mqtt' signal correctly schedules the runners.
    """
    configs = [
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        )
    ]
    _ = automation_handler_factory(configs)

    mqtt_message_received.send(None, message=mqtt_message_plain)

    mock_create_task.assert_called_once()

    coro = mock_create_task.call_args[0][0]
    await coro

    mock_run_all_runners.assert_called_once_with(mqtt_message_plain)


@pytest.mark.asyncio
async def test_handle_state_change_does_nothing_if_no_new_state(
    automation_handler_factory,
):
    """
    Test that the state change handler does nothing if 'new_state' is missing.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []})
    ]
    handler = automation_handler_factory(configs)

    handler._run_all_runners = AsyncMock()

    switchbot_advertisement_received.send(None, new_state=None)
    switchbot_advertisement_received.send(None)  # no kwargs

    await asyncio.sleep(0)  # allow any potential tasks to run
    handler._run_all_runners.assert_not_called()


@pytest.mark.asyncio
async def test_handle_mqtt_message_does_nothing_if_no_message(
    automation_handler_factory,
):
    """
    Test that the MQTT handler does nothing if 'message' is missing.
    """
    configs = [
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        )
    ]
    handler = automation_handler_factory(configs)

    handler._run_all_runners = AsyncMock()

    mqtt_message_received.send(None, message=None)
    mqtt_message_received.send(None)  # no kwargs

    await asyncio.sleep(0)
    handler._run_all_runners.assert_not_called()


@pytest.mark.asyncio
async def test_run_all_runners_concurrently(
    automation_handler_factory, mock_switchbot_advertisement
):
    """
    Test that all runners are executed concurrently.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
    ]
    handler = automation_handler_factory(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._action_runners[0].run = mock_run_1
    handler._action_runners[1].run = mock_run_2

    new_state = mock_switchbot_advertisement()
    await handler._run_all_runners(new_state)

    mock_run_1.assert_awaited_once_with(new_state)
    mock_run_2.assert_awaited_once_with(new_state)


@pytest.mark.asyncio
async def test_run_all_runners_handles_exceptions(
    automation_handler_factory, mock_switchbot_advertisement, caplog
):
    """
    Test that _run_all_runners handles exceptions from individual runners
    without stopping other runners and logs the error.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
    ]
    handler = automation_handler_factory(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock(side_effect=ValueError("Test exception"))
    mock_run_3 = AsyncMock()

    handler._action_runners[0].run = mock_run_1
    handler._action_runners[1].run = mock_run_2
    handler._action_runners[2].run = mock_run_3

    new_state = mock_switchbot_advertisement()

    with caplog.at_level(logging.ERROR):
        await handler._run_all_runners(new_state)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(new_state)
        mock_run_2.assert_awaited_once_with(new_state)
        mock_run_3.assert_awaited_once_with(new_state)

        # Assert that the exception was logged
        assert len(caplog.records) == 1
        assert (
            "An action runner failed with an exception: Test exception" in caplog.text
        )
        assert caplog.records[0].levelname == "ERROR"
        assert (
            "An action runner failed with an exception: Test exception"
            in caplog.records[0].message
        )
