# tests/test_dispatcher.py
from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.dispatcher import EventDispatcher


@pytest.fixture
def mock_advertisement():
    """Provides a generic mock advertisement for dispatcher tests."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:AA:BB"
    return adv


@pytest.fixture
def actions_config():
    """Provides a sample actions configuration."""
    return [
        {
            "name": "Test Edge-Trigger Action",
            "cooldown": "1s",
            "conditions": {"state": {"dummy": True}},
            "trigger": {"type": "any"},
        }
    ]


@patch("switchbot_actions.triggers.trigger_action")
@patch("time.time")
def test_dispatcher_edge_trigger_behavior(
    mock_time, mock_trigger_action, mock_advertisement, actions_config
):
    """
    Test that EventDispatcher fires only on the False -> True transition.
    """
    dispatcher = EventDispatcher(actions_config=actions_config)

    with patch("switchbot_actions.triggers.check_conditions") as mock_check_conditions:
        # 1. First event: condition is False -> should not trigger
        mock_time.return_value = 1000
        mock_check_conditions.return_value = False
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_not_called()

        # 2. Second event: condition becomes True -> should trigger
        mock_time.return_value = 1001
        mock_check_conditions.return_value = True
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()

        # 3. Third event: condition stays True
        # -> should NOT trigger again (still on cooldown)
        mock_time.return_value = 1001.5
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()  # Still called only once

        # 4. Fourth event: condition becomes False -> should not trigger
        mock_time.return_value = 1002
        mock_check_conditions.return_value = False
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()  # Still called only once

        # 5. Fifth event: condition becomes True again -> should trigger again
        mock_time.return_value = 1003
        mock_check_conditions.return_value = True
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        assert mock_trigger_action.call_count == 2


@patch("switchbot_actions.triggers.trigger_action")
@patch("time.time")
def test_dispatcher_cooldown(
    mock_time, mock_trigger_action, mock_advertisement, actions_config
):
    """Test that cooldown prevents an action from firing."""
    dispatcher = EventDispatcher(actions_config=actions_config)

    with patch("switchbot_actions.triggers.check_conditions") as mock_check_conditions:
        # --- First Trigger ---
        # Event 1: condition is False
        mock_time.return_value = 999
        mock_check_conditions.return_value = False
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_not_called()

        # Event 2: condition becomes True -> should trigger
        mock_time.return_value = 1000
        mock_check_conditions.return_value = True
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()

        # --- Cooldown Period ---
        # Event 3: condition goes False
        mock_time.return_value = 1000.2
        mock_check_conditions.return_value = False
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()  # Count is still 1

        # Event 4: condition becomes True again, but inside cooldown (1s)
        # -> should NOT trigger
        mock_time.return_value = 1000.5
        mock_check_conditions.return_value = True
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()  # Count is still 1

        # --- After Cooldown ---
        # Event 5: condition goes False again
        mock_time.return_value = 1001
        mock_check_conditions.return_value = False
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        mock_trigger_action.assert_called_once()  # Count is still 1

        # Event 6: condition becomes True, after cooldown -> should trigger
        mock_time.return_value = 1002
        mock_check_conditions.return_value = True
        dispatcher.handle_signal(None, new_data=mock_advertisement)
        assert mock_trigger_action.call_count == 2
