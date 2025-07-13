# tests/test_store.py
from unittest.mock import MagicMock

import pytest

from switchbot_actions.signals import advertisement_received
from switchbot_actions.store import DeviceStateStore


@pytest.fixture
def store():
    """Provides a fresh DeviceStateStore for each test."""
    return DeviceStateStore()


@pytest.fixture
def mock_advertisement():
    """Creates a mock SwitchBotAdvertisement object."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:00:01"
    adv.data = {
        "modelName": "WoSensorTH",
        "temperature": 25.5,
        "humidity": 50,
        "battery": 99,
    }
    return adv


def test_store_initialization(store):
    """Test that the store is initialized empty."""
    assert store.get_all_states() == {}


def test_handle_advertisement(store, mock_advertisement):
    """Test that the store correctly handles a new advertisement signal."""
    advertisement_received.send(None, new_data=mock_advertisement)

    assert len(store.get_all_states()) == 1
    stored_state = store.get_state("DE:AD:BE:EF:00:01")
    assert stored_state is not None
    assert stored_state.address == "DE:AD:BE:EF:00:01"
    assert stored_state.data["temperature"] == 25.5


def test_get_state(store, mock_advertisement):
    """Test retrieving a specific state by address."""
    assert store.get_state("DE:AD:BE:EF:00:01") is None
    advertisement_received.send(None, new_data=mock_advertisement)
    assert store.get_state("DE:AD:BE:EF:00:01") == mock_advertisement


def test_get_all_states(store, mock_advertisement):
    """Test retrieving all states."""
    assert store.get_all_states() == {}
    advertisement_received.send(None, new_data=mock_advertisement)
    assert store.get_all_states() == {"DE:AD:BE:EF:00:01": mock_advertisement}


def test_state_overwrite(store, mock_advertisement):
    """Test that a new advertisement for the same device overwrites the old state."""
    advertisement_received.send(None, new_data=mock_advertisement)

    updated_advertisement = MagicMock()
    updated_advertisement.address = "DE:AD:BE:EF:00:01"
    updated_advertisement.data = {
        "modelName": "WoSensorTH",
        "temperature": 26.0,  # Updated temperature
        "humidity": 51,
        "battery": 98,
    }

    advertisement_received.send(None, new_data=updated_advertisement)

    assert len(store.get_all_states()) == 1
    new_state = store.get_state("DE:AD:BE:EF:00:01")
    assert new_state.data["temperature"] == 26.0
    assert new_state.data["battery"] == 98
