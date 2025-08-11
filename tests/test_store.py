# tests/test_store.py
import pytest

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


@pytest.mark.asyncio
async def test_storage_initialization(storage):
    """Test that the storage is initialized empty."""
    assert await storage.get_all() == {}


@pytest.mark.asyncio
async def test_update_and_get_state(storage, mock_state):
    """
    Test that the store correctly updates and retrieves state.
    """
    key = "DE:AD:BE:EF:00:01"
    await storage.get_and_update(key, mock_state)

    assert len(await storage.get_all()) == 1
    stored_state = await storage.get(key)
    assert stored_state is not None
    assert stored_state.address == "DE:AD:BE:EF:00:01"
    assert stored_state.data["data"]["temperature"] == 25.5


@pytest.mark.asyncio
async def test_get_state_non_existent(storage):
    """Test retrieving a non-existent state by key."""
    assert await storage.get("NON_EXISTENT_KEY") is None


@pytest.mark.asyncio
async def test_get_all_empty(storage):
    """Test retrieving all states when empty."""
    assert await storage.get_all() == {}


@pytest.mark.asyncio
async def test_get_all_with_data(storage, mock_state):
    """Test retrieving all states with data."""
    key = "DE:AD:BE:EF:00:01"
    await storage.get_and_update(key, mock_state)
    assert await storage.get_all() == {key: mock_state}


@pytest.mark.asyncio
async def test_state_overwrite(storage, mock_state, mock_switchbot_advertisement):
    """Test that a new state for the same key overwrites the old state."""
    key = "DE:AD:BE:EF:00:01"
    await storage.get_and_update(key, mock_state)

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

    await storage.get_and_update(key, updated_state)

    assert len(await storage.get_all()) == 1
    new_state = await storage.get(key)
    assert new_state.data["data"]["temperature"] == 26.0
    assert new_state.data["data"]["battery"] == 98


@pytest.mark.asyncio
async def test_get_and_update_state(storage, mock_state, mock_switchbot_advertisement):
    """Test that get_and_update atomically retrieves the old state and updates with
    the new."""
    key = "DE:AD:BE:EF:00:02"
    initial_state = mock_state

    # First call: key does not exist, should return None and set the state
    old_state = await storage.get_and_update(key, initial_state)
    assert old_state is None
    assert await storage.get(key) == initial_state

    # Second call: key exists, should return the initial_state and set the updated_state
    updated_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:00:02",
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 27.0, "humidity": 55, "battery": 90},
        },
    )
    old_state = await storage.get_and_update(key, updated_state)
    assert old_state == initial_state
    assert await storage.get(key) == updated_state

    # Verify that other keys are unaffected
    assert len(await storage.get_all()) == 1
