# tests/test_handlers.py
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationRule
from switchbot_actions.evaluator import MqttState, SwitchBotState, create_state_object
from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.mqtt import mqtt_message_received
from switchbot_actions.signals import switchbot_advertisement_received
from switchbot_actions.store import StateStore
from switchbot_actions.triggers import DurationTrigger, EdgeTrigger

# --- Fixtures ---


@pytest.fixture
def state_store():
    """Returns a mock StateStore object."""
    return MagicMock(spec=StateStore)


@pytest.fixture
def automation_handler_factory(state_store):
    """
    A factory fixture to create isolated AutomationHandler instances for each test.
    Ensures that signal connections are torn down after each test.
    """
    created_handlers = []

    def factory(configs: list[AutomationRule]) -> AutomationHandler:
        handler = AutomationHandler(configs=configs, state_store=state_store)
        created_handlers.append(handler)
        return handler

    yield factory

    # Teardown: Disconnect all created handlers from signals after the test runs
    for handler in created_handlers:
        switchbot_advertisement_received.disconnect(handler.handle_switchbot_event)
        mqtt_message_received.disconnect(handler.handle_mqtt_event)


# --- Tests ---


def test_init_creates_correct_action_runners(automation_handler_factory):
    """
    Test that the handler initializes the correct type of runners based on config.
    """
    with patch("switchbot_actions.handlers.create_action_executor") as mock_factory:
        mock_factory.return_value = MagicMock(name="ActionExecutorMock")

        then_block = [{"type": "shell_command", "command": "echo 'hi'"}]
        configs = [
            AutomationRule.model_validate(
                {"if": {"source": "switchbot"}, "then": then_block}
            ),
            AutomationRule.model_validate(
                {
                    "if": {"source": "switchbot_timer", "duration": "1s"},
                    "then": then_block,
                }
            ),
            AutomationRule.model_validate(
                {"if": {"source": "mqtt", "topic": "test"}, "then": then_block}
            ),
            AutomationRule.model_validate(
                {
                    "if": {"source": "mqtt_timer", "topic": "test", "duration": "1s"},
                    "then": then_block,
                }
            ),
        ]

        handler = automation_handler_factory(configs)

        assert len(handler._switchbot_runners) == 2
        assert len(handler._mqtt_runners) == 2
        assert mock_factory.call_count == 4  # 4 rules, each with 1 action

        # Verify trigger types directly from the handler's runners
        assert isinstance(handler._switchbot_runners[0]._trigger, EdgeTrigger)
        assert isinstance(handler._switchbot_runners[1]._trigger, DurationTrigger)
        assert isinstance(handler._mqtt_runners[0]._trigger, EdgeTrigger)
        assert isinstance(handler._mqtt_runners[1]._trigger, DurationTrigger)


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.create_state_object")
@patch(
    "switchbot_actions.handlers.AutomationHandler._run_switchbot_runners",
    new_callable=AsyncMock,
)
@patch("switchbot_actions.handlers.asyncio.create_task")
async def test_handle_switchbot_event_schedules_runner_task(
    mock_create_task,
    mock_run_switchbot_runners,
    mock_create_state_object,
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

    raw_state = mock_switchbot_advertisement()
    mock_create_state_object.return_value = MagicMock(spec=SwitchBotState)

    switchbot_advertisement_received.send(None, new_state=raw_state)

    mock_create_state_object.assert_called_once_with(raw_state)
    mock_create_task.assert_called_once()

    coro = mock_create_task.call_args[0][0]
    await coro

    mock_run_switchbot_runners.assert_called_once_with(
        mock_create_state_object.return_value
    )


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.create_state_object")
@patch(
    "switchbot_actions.handlers.AutomationHandler._run_mqtt_runners",
    new_callable=AsyncMock,
)
@patch("switchbot_actions.handlers.asyncio.create_task")
async def test_handle_mqtt_message_schedules_runner_task(
    mock_create_task,
    mock_run_mqtt_runners,
    mock_create_state_object,
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

    state_object_mock = MagicMock(spec=MqttState)
    mock_create_state_object.return_value = state_object_mock

    mqtt_message_received.send(None, message=mqtt_message_plain)

    mock_create_state_object.assert_called_once_with(mqtt_message_plain)
    mock_create_task.assert_called_once()

    coro = mock_create_task.call_args[0][0]
    await coro

    mock_run_mqtt_runners.assert_called_once_with(state_object_mock)


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

    handler._run_switchbot_runners = AsyncMock()

    switchbot_advertisement_received.send(None, new_state=None)
    switchbot_advertisement_received.send(None)  # no kwargs

    await asyncio.sleep(0)  # allow any potential tasks to run
    handler._run_switchbot_runners.assert_not_called()


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

    handler._run_mqtt_runners = AsyncMock()

    mqtt_message_received.send(None, message=None)
    mqtt_message_received.send(None)  # no kwargs

    await asyncio.sleep(0)
    handler._run_mqtt_runners.assert_not_called()


@pytest.mark.asyncio
async def test_run_switchbot_runners_concurrently(
    automation_handler_factory, mock_switchbot_advertisement
):
    """
    Test that switchbot runners are executed concurrently.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
    ]
    handler = automation_handler_factory(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._switchbot_runners[0].run = mock_run_1
    handler._switchbot_runners[1].run = mock_run_2

    raw_state = mock_switchbot_advertisement()
    state = create_state_object(raw_state)
    await handler._run_switchbot_runners(state)

    mock_run_1.assert_awaited_once_with(state)
    mock_run_2.assert_awaited_once_with(state)


@pytest.mark.asyncio
async def test_run_mqtt_runners_concurrently(
    automation_handler_factory, mqtt_message_plain
):
    """
    Test that mqtt runners are executed concurrently.
    """
    configs = [
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        ),
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        ),
    ]
    handler = automation_handler_factory(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._mqtt_runners[0].run = mock_run_1
    handler._mqtt_runners[1].run = mock_run_2

    state = create_state_object(mqtt_message_plain)
    await handler._run_mqtt_runners(state)

    mock_run_1.assert_awaited_once_with(state)
    mock_run_2.assert_awaited_once_with(state)


@pytest.mark.asyncio
async def test_run_switchbot_runners_handles_exceptions(
    automation_handler_factory, mock_switchbot_advertisement, caplog
):
    """
    Test that _run_switchbot_runners handles exceptions from individual runners
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

    handler._switchbot_runners[0].run = mock_run_1
    handler._switchbot_runners[1].run = mock_run_2
    handler._switchbot_runners[2].run = mock_run_3

    raw_state = mock_switchbot_advertisement()
    state = create_state_object(raw_state)

    with caplog.at_level(logging.ERROR):
        await handler._run_switchbot_runners(state)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state)
        mock_run_2.assert_awaited_once_with(state)
        mock_run_3.assert_awaited_once_with(state)

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


@pytest.mark.asyncio
async def test_run_mqtt_runners_handles_exceptions(
    automation_handler_factory, mqtt_message_plain, caplog
):
    """
    Test that _run_mqtt_runners handles exceptions from individual runners
    without stopping other runners and logs the error.
    """
    configs = [
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        ),
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        ),
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        ),
    ]
    handler = automation_handler_factory(configs)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock(side_effect=ValueError("Test exception"))
    mock_run_3 = AsyncMock()

    handler._mqtt_runners[0].run = mock_run_1
    handler._mqtt_runners[1].run = mock_run_2
    handler._mqtt_runners[2].run = mock_run_3

    state = create_state_object(mqtt_message_plain)

    with caplog.at_level(logging.ERROR):
        await handler._run_mqtt_runners(state)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state)
        mock_run_2.assert_awaited_once_with(state)
        mock_run_3.assert_awaited_once_with(state)

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
