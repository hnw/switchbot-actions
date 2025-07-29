# tests/test_store.py
from unittest.mock import patch

import pytest

from switchbot_actions.signals import switchbot_advertisement_received
from switchbot_actions.store import StateStore


@pytest.fixture
def storage():
    """Provides a fresh StateStore for each test."""
    return StateStore()


@pytest.fixture
def mock_state(mock_switchbot_advertisement):
    """Creates a mock state object that behaves like a SwitchBotAdvertisement."""
    state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 25.5, "humidity": 50, "battery": 99},
        },
    )
    return state


def test_storage_initialization(storage):
    """Test that the storage is initialized empty."""
    assert storage.get_all_states() == {}


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.AutomationHandler")
async def test_handle_state_change(mock_automation_handler, storage, mock_state):
    """
    Test that the store correctly handles a new switchbot_advertisement_received signal.
    """
    switchbot_advertisement_received.send(None, new_state=mock_state)

    assert len(storage.get_all_states()) == 1
    stored_state = storage.get_state("DE:AD:BE:EF:00:01")
    assert stored_state is not None
    assert stored_state.address == "DE:AD:BE:EF:00:01"
    assert stored_state.data["data"]["temperature"] == 25.5


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.AutomationHandler")
async def test_get_state(mock_automation_handler, storage, mock_state):
    """Test retrieving a specific state by key."""
    assert storage.get_state("DE:AD:BE:EF:00:01") is None
    switchbot_advertisement_received.send(None, new_state=mock_state)
    assert storage.get_state("DE:AD:BE:EF:00:01") == mock_state


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.AutomationHandler")
async def test_get_all_states(mock_automation_handler, storage, mock_state):
    """Test retrieving all states."""
    assert storage.get_all_states() == {}
    switchbot_advertisement_received.send(None, new_state=mock_state)
    assert storage.get_all_states() == {"DE:AD:BE:EF:00:01": mock_state}


@pytest.mark.asyncio
@patch("switchbot_actions.handlers.AutomationHandler")
async def test_state_overwrite(
    mock_automation_handler, storage, mock_state, mock_switchbot_advertisement
):
    """Test that a new state for the same key overwrites the old state."""
    switchbot_advertisement_received.send(None, new_state=mock_state)

    updated_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:01",
        data={
            "modelName": "WoSensorTH",
            "data": {
                "temperature": 26.0,  # Updated temperature
                "humidity": 51,
                "battery": 98,
            },
        },
    )

    switchbot_advertisement_received.send(None, new_state=updated_state)

    assert len(storage.get_all_states()) == 1
    new_state = storage.get_state("DE:AD:BE:EF:00:01")
    assert new_state.data["data"]["temperature"] == 26.0
    assert new_state.data["data"]["battery"] == 98
