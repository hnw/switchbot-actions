# tests/test_timers.py
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from switchbot_exporter.timers import TimerHandler
from switchbot_exporter.store import DeviceStateStore
from switchbot_exporter.signals import advertisement_received

pytestmark = pytest.mark.asyncio

def consume_coroutine_and_return_mock_task(coro):
    """Consumes a coroutine to prevent 'never awaited' warnings and returns a mock for test assertions."""
    coro.close()
    return MagicMock()

@pytest.fixture
def mock_store():
    """Provides a mock DeviceStateStore."""
    return MagicMock(spec=DeviceStateStore)

@pytest.fixture
def mock_advertisement():
    """Creates a mock SwitchBotAdvertisement."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:AA:BB"
    adv.data = {
        'modelName': 'WoContact',
        'data': {'contact_open': True}
    }
    return adv

@pytest.fixture
def timer_config():
    """Provides a sample timer configuration."""
    return [{
        "name": "Door Open Alert",
        "conditions": {"state": {"contact_open": True}},
        "duration": "0.01s",
        "trigger": {"type": "shell_command"}
    }]

@patch('switchbot_exporter.triggers.check_conditions', return_value=True)
async def test_timer_task_starts_when_conditions_met(mock_check, timer_config, mock_store, mock_advertisement):
    """Test that an asyncio.Task is created when timer conditions are met."""
    handler = TimerHandler(timers_config=timer_config, store=mock_store)
    assert not handler._active_timers

    with patch('asyncio.create_task', side_effect=consume_coroutine_and_return_mock_task) as mock_create_task:
        advertisement_received.send(None, new_data=mock_advertisement)
        mock_create_task.assert_called_once()
        assert len(handler._active_timers) == 1

@patch('switchbot_exporter.triggers.check_conditions', return_value=False)
async def test_timer_task_cancels_when_conditions_not_met(mock_check, timer_config, mock_store, mock_advertisement):
    """Test that a running asyncio.Task is cancelled if conditions are no longer met."""
    handler = TimerHandler(timers_config=timer_config, store=mock_store)
    
    # Manually add a mock task to simulate it running
    mock_task = MagicMock()
    timer_key = ("Door Open Alert", mock_advertisement.address)
    handler._active_timers[timer_key] = mock_task
    assert len(handler._active_timers) == 1

    # Signal that conditions are no longer met
    advertisement_received.send(None, new_data=mock_advertisement)
    
    mock_task.cancel.assert_called_once()
    assert not handler._active_timers

@patch('switchbot_exporter.triggers.trigger_action')
async def test_timer_run_triggers_action(mock_trigger_action, timer_config, mock_store, mock_advertisement):
    """Test that the _run_timer coroutine triggers an action after sleeping."""
    mock_store.get_state.return_value = mock_advertisement
    handler = TimerHandler(timers_config=timer_config, store=mock_store)

    # Directly call the coroutine
    await handler._run_timer(timer_config[0], mock_advertisement.address, 0.01)
    
    mock_trigger_action.assert_called_once()


