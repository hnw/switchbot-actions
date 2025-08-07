# tests/test_handlers.py
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationRule
from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.state import (
    create_state_object_with_previous,
)
from switchbot_actions.store import StateStore
from switchbot_actions.triggers import DurationTrigger, EdgeTrigger

# --- Fixtures ---


@pytest.fixture
def state_store():
    """Returns a mock StateStore object."""
    mock_store = AsyncMock(spec=StateStore)
    mock_store.get.return_value = None  # Default for build_state_with_previous
    mock_store.get_and_update.return_value = None  # Ensure previous_raw_event is None
    return mock_store


@pytest.fixture
def automation_handler_factory(state_store):
    """
    A factory fixture to create isolated AutomationHandler instances for each test.
    """

    def factory(configs: list[AutomationRule]) -> AutomationHandler:
        handler = AutomationHandler(configs=configs, state_store=state_store)
        return handler

    yield factory


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
async def test_handle_switchbot_event_schedules_runner_task(
    automation_handler_factory,
    mock_switchbot_advertisement,
    state_store,
):
    """
    Test that a 'switchbot' signal correctly schedules the runners.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []})
    ]
    handler = automation_handler_factory(configs)

    # Ensure get_and_update returns None to prevent TypeError
    handler._state_store.get_and_update.return_value = None

    # Mock the internal async method that gets called by create_task
    handler._run_switchbot_runners = AsyncMock()

    raw_state = mock_switchbot_advertisement(address="test_address")
    handler.handle_switchbot_event(None, new_state=raw_state)

    # Allow the scheduled task to run
    await asyncio.sleep(0)

    # Assert that the internal method was called with the correct state object
    expected_state_object = create_state_object_with_previous(raw_state, None)
    handler._run_switchbot_runners.assert_awaited_once()
    actual_state_object = handler._run_switchbot_runners.call_args[0][0]
    assert (
        actual_state_object.get_values_dict() == expected_state_object.get_values_dict()
    )


@pytest.mark.asyncio
async def test_handle_mqtt_message_schedules_runner_task(
    automation_handler_factory,
    mqtt_message_plain,
    state_store,
):
    """
    Test that an 'mqtt' signal correctly schedules the runners.
    """
    configs = [
        AutomationRule.model_validate(
            {"if": {"source": "mqtt", "topic": "#"}, "then": []}
        )
    ]
    handler = automation_handler_factory(configs)

    # Ensure get_and_update returns None to prevent TypeError
    handler._state_store.get_and_update.return_value = None

    # Mock the internal async method that gets called by create_task
    handler._run_mqtt_runners = AsyncMock()

    raw_message = mqtt_message_plain
    handler.handle_mqtt_event(None, message=raw_message)

    # Allow the scheduled task to run
    await asyncio.sleep(0)

    # Assert that the internal method was called with the correct state object
    expected_state_object = create_state_object_with_previous(raw_message, None)
    handler._run_mqtt_runners.assert_awaited_once()
    actual_state_object = handler._run_mqtt_runners.call_args[0][0]
    assert (
        actual_state_object.get_values_dict() == expected_state_object.get_values_dict()
    )


@pytest.mark.asyncio
@patch("asyncio.create_task")
async def test_handle_state_change_does_nothing_if_no_new_state(
    mock_create_task,
    automation_handler_factory,
):
    """
    Test that the state change handler does nothing if 'new_state' is missing.
    """
    configs = [
        AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []})
    ]
    handler = automation_handler_factory(configs)

    handler.handle_switchbot_event(None, new_state=None)
    handler.handle_switchbot_event(None)  # no kwargs

    mock_create_task.assert_not_called()


@pytest.mark.asyncio
@patch("asyncio.create_task")
async def test_handle_mqtt_message_does_nothing_if_no_message(
    mock_create_task,
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

    handler.handle_mqtt_event(None, message=None)
    handler.handle_mqtt_event(None)  # no kwargs

    mock_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_switchbot_runners_concurrently(
        automation_handler_factory, mock_switchbot_advertisement, state_store
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
        state_object = create_state_object_with_previous(raw_state, None)
        await handler._run_switchbot_runners(state_object)

        mock_run_1.assert_awaited_once_with(state_object)
        mock_run_2.assert_awaited_once_with(state_object)


@pytest.mark.asyncio
async def test_run_mqtt_runners_concurrently(
    automation_handler_factory, mqtt_message_plain, state_store
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

    state_object = create_state_object_with_previous(mqtt_message_plain, None)

    await handler._run_mqtt_runners(state_object)

    mock_run_1.assert_awaited_once_with(state_object)
    mock_run_2.assert_awaited_once_with(state_object)


@pytest.mark.asyncio
async def test_run_switchbot_runners_handles_exceptions(
    automation_handler_factory, mock_switchbot_advertisement, caplog, state_store
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
    state_object = create_state_object_with_previous(raw_state, None)

    with caplog.at_level(logging.ERROR):
        await handler._run_switchbot_runners(state_object)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state_object)
        mock_run_2.assert_awaited_once_with(state_object)
        mock_run_3.assert_awaited_once_with(state_object)

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
    automation_handler_factory, mqtt_message_plain, caplog, state_store
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

    state_object = create_state_object_with_previous(mqtt_message_plain, None)

    with caplog.at_level(logging.ERROR):
        await handler._run_mqtt_runners(state_object)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state_object)
        mock_run_2.assert_awaited_once_with(state_object)
        mock_run_3.assert_awaited_once_with(state_object)

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
