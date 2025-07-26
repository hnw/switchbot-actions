# tests/test_store.py
from unittest.mock import patch

import pytest

from switchbot_actions.signals import state_changed
from switchbot_actions.store import StateStorage


@pytest.fixture
def storage():
    """Provides a fresh StateStorage for each test."""
    return StateStorage()


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


def test_handle_state_change(storage, mock_state):
    """Test that the store correctly handles a new state_changed signal."""
    with patch(
        "switchbot_actions.signals.state_changed.connect"
    ):  # Prevent AutomationHandler from connecting
        state_changed.send(None, new_state=mock_state)

    assert len(storage.get_all_states()) == 1
    stored_state = storage.get_state("DE:AD:BE:EF:00:01")
    assert stored_state is not None
    assert stored_state.address == "DE:AD:BE:EF:00:01"
    assert stored_state.data["data"]["temperature"] == 25.5


def test_get_state(storage, mock_state):
    """Test retrieving a specific state by key."""
    assert storage.get_state("DE:AD:BE:EF:00:01") is None
    with patch(
        "switchbot_actions.signals.state_changed.connect"
    ):  # Prevent AutomationHandler from connecting
        state_changed.send(None, new_state=mock_state)
    assert storage.get_state("DE:AD:BE:EF:00:01") == mock_state


def test_get_all_states(storage, mock_state):
    """Test retrieving all states."""
    assert storage.get_all_states() == {}
    with patch(
        "switchbot_actions.signals.state_changed.connect"
    ):  # Prevent AutomationHandler from connecting
        state_changed.send(None, new_state=mock_state)
    assert storage.get_all_states() == {"DE:AD:BE:EF:00:01": mock_state}


def test_state_overwrite(storage, mock_state, mock_switchbot_advertisement):
    """Test that a new state for the same key overwrites the old state."""
    with patch(
        "switchbot_actions.signals.state_changed.connect"
    ):  # Prevent AutomationHandler from connecting
        state_changed.send(None, new_state=mock_state)

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

        state_changed.send(None, new_state=updated_state)

    assert len(storage.get_all_states()) == 1
    new_state = storage.get_state("DE:AD:BE:EF:00:01")
    assert new_state.data["data"]["temperature"] == 26.0
    assert new_state.data["data"]["battery"] == 98
