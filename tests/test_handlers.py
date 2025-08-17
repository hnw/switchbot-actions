# tests/test_handlers.py
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import AutomationRule, AutomationSettings
from switchbot_actions.handlers import AutomationHandler
from switchbot_actions.state import (
    create_state_object,
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
    mock_store.get_all = AsyncMock(return_value={})  # Mock get_all method
    return mock_store


@pytest.fixture
def automation_handler_factory(state_store):
    """
    A factory fixture to create isolated AutomationHandler instances for each test.
    """

    def factory(settings: AutomationSettings) -> AutomationHandler:
        handler = AutomationHandler(settings=settings, state_store=state_store)
        return handler

    yield factory


# --- Tests ---


def test_init_creates_correct_action_runners(automation_handler_factory):
    """
    Test that the handler initializes the correct type of runners based on config.
    """
    with patch("switchbot_actions.handlers.create_action_executor") as mock_factory:
        mock_factory.return_value = MagicMock(name="ActionExecutorMock")

        then_block = [{"type": "shell_command", "command": ["echo", "hi"]}]
        configs = [
            AutomationRule.model_validate(
                {"if": {"source": "switchbot"}, "then": then_block}
            ),
            AutomationRule.model_validate(
                {
                    "if": {"source": "switchbot", "duration": "1s"},
                    "then": then_block,
                }
            ),
            AutomationRule.model_validate(
                {"if": {"source": "mqtt", "topic": "test"}, "then": then_block}
            ),
            AutomationRule.model_validate(
                {
                    "if": {"source": "mqtt", "topic": "test", "duration": "1s"},
                    "then": then_block,
                }
            ),
        ]

        # Modified line
        settings = AutomationSettings(rules=configs)
        handler = automation_handler_factory(settings)

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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Ensure get_and_update returns None to prevent TypeError
    handler._state_store.get_and_update.return_value = None

    # Mock the internal async method that gets called by create_task
    handler._run_switchbot_runners = AsyncMock()

    raw_state = mock_switchbot_advertisement(address="test_address")
    handler.handle_switchbot_event(None, new_state=raw_state)

    # Allow the scheduled task to run
    await asyncio.sleep(0)

    # Assert that the internal method was called with the correct state object
    expected_state_object = create_state_object(raw_state, previous=None)
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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Ensure get_and_update returns None to prevent TypeError
    handler._state_store.get_and_update.return_value = None

    # Mock the internal async method that gets called by create_task
    handler._run_mqtt_runners = AsyncMock()

    raw_message = mqtt_message_plain
    handler.handle_mqtt_event(None, message=raw_message)

    # Allow the scheduled task to run
    await asyncio.sleep(0)

    # Assert that the internal method was called with the correct state object
    expected_state_object = create_state_object(raw_message, previous=None)
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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    handler.handle_switchbot_event(None, new_state=None)

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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    handler.handle_mqtt_event(None, message=None)

    mock_create_task.assert_not_called()


@pytest.mark.asyncio
async def test_automation_handler_lifecycle_connects_and_disconnects_signals(
    automation_handler_factory,
):
    """
    Test that AutomationHandler's start/stop methods correctly connect/disconnect
    signals.
    """
    with (
        patch(
            "switchbot_actions.handlers.switchbot_advertisement_received"
        ) as mock_switchbot_signal,
        patch("switchbot_actions.handlers.mqtt_message_received") as mock_mqtt_signal,
    ):
        # Create a handler with some dummy configs to ensure it initializes runners
        configs = [
            AutomationRule.model_validate({"if": {"source": "switchbot"}, "then": []}),
            AutomationRule.model_validate(
                {"if": {"source": "mqtt", "topic": "#"}, "then": []}
            ),
        ]
        # Modified line
        settings = AutomationSettings(rules=configs)
        handler = automation_handler_factory(settings)

        # Test start(): signals should be connected
        await handler.start()
        mock_switchbot_signal.connect.assert_called_once_with(
            handler.handle_switchbot_event
        )
        mock_mqtt_signal.connect.assert_called_once_with(handler.handle_mqtt_event)

        # Reset mocks for stop() assertions
        mock_switchbot_signal.connect.reset_mock()
        mock_mqtt_signal.connect.reset_mock()
        mock_switchbot_signal.disconnect.reset_mock()
        mock_mqtt_signal.disconnect.reset_mock()

        # Test stop(): signals should be disconnected
        await handler.stop()
        mock_switchbot_signal.disconnect.assert_called_once_with(
            handler.handle_switchbot_event
        )
        mock_mqtt_signal.disconnect.assert_called_once_with(handler.handle_mqtt_event)

        # Ensure connect was not called again during stop
        mock_switchbot_signal.connect.assert_not_called()
        mock_mqtt_signal.connect.assert_not_called()


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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._switchbot_runners[0].run = mock_run_1
    handler._switchbot_runners[1].run = mock_run_2

    raw_state = mock_switchbot_advertisement()
    state_object = create_state_object(raw_state, previous=None)
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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock()
    handler._mqtt_runners[0].run = mock_run_1
    handler._mqtt_runners[1].run = mock_run_2

    state_object = create_state_object(mqtt_message_plain, previous=None)

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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock(side_effect=ValueError("Test exception"))
    mock_run_3 = AsyncMock()

    handler._switchbot_runners[0].run = mock_run_1
    handler._switchbot_runners[1].run = mock_run_2
    handler._switchbot_runners[2].run = mock_run_3

    raw_state = mock_switchbot_advertisement()
    state_object = create_state_object(raw_state, previous=None)

    with caplog.at_level(logging.ERROR):
        await handler._run_switchbot_runners(state_object)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state_object)
        mock_run_2.assert_awaited_once_with(state_object)
        mock_run_3.assert_awaited_once_with(state_object)

        # Assert that the exception was logged
        assert len(caplog.records) == 1
        assert (
            "Failed to execute action due to a template error: Test exception"
            in caplog.text
        )
        assert caplog.records[0].levelname == "ERROR"
        assert (
            "Failed to execute action due to a template error: Test exception"
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
    # Modified line
    settings = AutomationSettings(rules=configs)
    handler = automation_handler_factory(settings)

    # Mock the run method of each runner
    mock_run_1 = AsyncMock()
    mock_run_2 = AsyncMock(side_effect=ValueError("Test exception"))
    mock_run_3 = AsyncMock()

    handler._mqtt_runners[0].run = mock_run_1
    handler._mqtt_runners[1].run = mock_run_2
    handler._mqtt_runners[2].run = mock_run_3

    state_object = create_state_object(mqtt_message_plain, previous=None)

    with caplog.at_level(logging.ERROR):
        await handler._run_mqtt_runners(state_object)

        # Assert that all runners were attempted to be run
        mock_run_1.assert_awaited_once_with(state_object)
        mock_run_2.assert_awaited_once_with(state_object)
        mock_run_3.assert_awaited_once_with(state_object)

        # Assert that the exception was logged
        assert len(caplog.records) == 1
        assert (
            "Failed to execute action due to a template error: Test exception"
            in caplog.text
        )
        assert caplog.records[0].levelname == "ERROR"
        assert (
            "Failed to execute action due to a template error: Test exception"
            in caplog.records[0].message
        )


@pytest.mark.asyncio
async def test_start_does_not_call__start_if_disabled(automation_handler_factory):
    """
    Tests that the public start() method does not call the internal _start()
    if the component is disabled by having no rules.
    """
    # AutomationHandler is disabled if there are no rules.
    disabled_settings = AutomationSettings(rules=[])
    handler = automation_handler_factory(disabled_settings)

    handler._start = AsyncMock()

    await handler.start()

    handler._start.assert_not_called()


# --- Added Tests for Reload Logic ---


@pytest.mark.asyncio
async def test_apply_live_update_reinitializes_runners(automation_handler_factory):
    """
    Tests that _apply_live_update correctly re-initializes the action runners
    when automation rules change.
    """
    # Initial settings with one switchbot rule
    initial_rules = [
        AutomationRule.model_validate(
            {"if": {"source": "switchbot"}, "then": [{"type": "log", "message": "a"}]}
        )
    ]
    initial_settings = AutomationSettings(rules=initial_rules)
    handler = automation_handler_factory(initial_settings)

    assert len(handler._switchbot_runners) == 1
    assert len(handler._mqtt_runners) == 0

    # New settings with one MQTT rule and one switchbot timer rule
    new_rules = [
        AutomationRule.model_validate(
            {
                "if": {"source": "mqtt", "topic": "#"},
                "then": [{"type": "log", "message": "b"}],
            }
        ),
        AutomationRule.model_validate(
            {
                "if": {"source": "switchbot", "duration": "5s"},
                "then": [{"type": "log", "message": "c"}],
            }
        ),
    ]
    new_settings = AutomationSettings(rules=new_rules)

    # Mock signal connect/disconnect to verify they are called during update
    with (
        patch(
            "switchbot_actions.handlers.switchbot_advertisement_received"
        ) as mock_switchbot_signal,
        patch("switchbot_actions.handlers.mqtt_message_received") as mock_mqtt_signal,
    ):
        await handler._apply_live_update(new_settings)

        # Verify signals were re-connected
        mock_switchbot_signal.disconnect.assert_called_once()
        mock_switchbot_signal.connect.assert_called_once()
        mock_mqtt_signal.disconnect.assert_called_once()
        mock_mqtt_signal.connect.assert_called_once()

    # Verify runners are updated
    assert len(handler._switchbot_runners) == 1
    assert len(handler._mqtt_runners) == 1
    assert isinstance(handler._switchbot_runners[0]._trigger, DurationTrigger)
    assert isinstance(handler._mqtt_runners[0]._trigger, EdgeTrigger)
