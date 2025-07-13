# tests/test_timers.py

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.store import DeviceStateStore
from switchbot_actions.timers import TimerHandler


@pytest.fixture
def mock_store():
    """Provides a mock DeviceStateStore."""
    return MagicMock(spec=DeviceStateStore)


@pytest.fixture
def mock_advertisement():
    """Creates a mock SwitchBotAdvertisement."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:AA:BB"
    return adv


@pytest.fixture
def timer_config():
    """Provides a sample timer configuration."""
    return [
        {
            "name": "One-Shot Timer",
            "conditions": {"state": {"dummy": True}},
            "duration": "0.01s",
            "cooldown": "1s",
            "trigger": {"type": "shell_command"},
        }
    ]


@pytest.mark.asyncio
async def test_timer_starts_on_false_to_true_transition(
    timer_config, mock_store, mock_advertisement
):
    """
    Test that a timer task is created only on the False -> True transition
    and that it gets cleaned up properly.
    """
    handler = TimerHandler(timers_config=timer_config, store=mock_store)
    timer_name = timer_config[0].get("name")
    device_address = mock_advertisement.address
    key = (timer_name, device_address)

    with patch("switchbot_actions.triggers.check_conditions") as mock_check:
        # 1. State is False -> no task
        mock_check.return_value = False
        handler.handle_signal(None, new_data=mock_advertisement)
        assert not handler._active_timers

        # 2. State becomes True -> task created
        mock_check.return_value = True
        handler.handle_signal(None, new_data=mock_advertisement)
        assert key in handler._active_timers
        assert isinstance(handler._active_timers[key], asyncio.Task)
        initial_task = handler._active_timers[key]

        # 3. State stays True -> no new task is created
        handler.handle_signal(None, new_data=mock_advertisement)
        assert len(handler._active_timers) == 1
        assert handler._active_timers[key] is initial_task

        # --- Cleanup ---
        # Explicitly cancel the created task to prevent RuntimeWarning
        task = handler._active_timers.pop(key)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # This is the expected outcome of cancellation.


@pytest.mark.asyncio
@patch("switchbot_actions.triggers.trigger_action")
async def test_timer_completes_and_triggers_action(
    mock_trigger_action, timer_config, mock_store, mock_advertisement
):
    """Test that a timer that runs to completion triggers its action."""
    mock_store.get_state.return_value = mock_advertisement
    handler = TimerHandler(timers_config=timer_config, store=mock_store)

    with patch("switchbot_actions.triggers.check_conditions", return_value=True):
        # Directly call _run_timer to simulate completion
        await handler._run_timer(timer_config[0], mock_advertisement.address, "0.01s")
        mock_trigger_action.assert_called_once()


def test_timer_cancels_on_true_to_false_transition(
    timer_config, mock_store, mock_advertisement
):
    """Test that a running timer is cancelled if the state becomes False."""
    handler = TimerHandler(timers_config=timer_config, store=mock_store)
    mock_task = MagicMock()
    key = (timer_config[0]["name"], mock_advertisement.address)
    handler._active_timers[key] = mock_task
    handler._last_condition_results[key] = True  # Pretend last state was True

    with patch("switchbot_actions.triggers.check_conditions", return_value=False):
        handler.handle_signal(None, new_data=mock_advertisement)
        mock_task.cancel.assert_called_once()
        assert not handler._active_timers  # Task should be removed
