# tests/test_dispatcher.py
import pytest
import time
from unittest.mock import MagicMock, patch
from switchbot_exporter.dispatcher import EventDispatcher

@pytest.fixture
def mock_advertisement():
    """Provides a generic mock advertisement for dispatcher tests."""
    return MagicMock()

@patch('switchbot_exporter.triggers.check_conditions', return_value=True)
@patch('switchbot_exporter.triggers.trigger_action')
def test_dispatcher_triggers_action(mock_trigger_action, mock_check_conditions, mock_advertisement):
    """Test that EventDispatcher calls trigger_action when conditions are met."""
    actions_config = [{
        "name": "Test Dispatcher Action",
        "conditions": {},
        "trigger": { 'type': 'any' }
    }]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_signal(None, new_data=mock_advertisement, old_data=None)
    
    mock_check_conditions.assert_called_once()
    mock_trigger_action.assert_called_once()

@patch('switchbot_exporter.triggers.check_conditions', return_value=False)
@patch('switchbot_exporter.triggers.trigger_action')
def test_dispatcher_does_not_trigger(mock_trigger_action, mock_check_conditions, mock_advertisement):
    """Test that EventDispatcher does NOT call trigger_action when conditions are not met."""
    actions_config = [{"name": "Test No-Trigger", "conditions": {}, "trigger": {}}]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_signal(None, new_data=mock_advertisement, old_data=None)
    
    mock_check_conditions.assert_called_once()
    mock_trigger_action.assert_not_called()

