# tests/test_scanner.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.scanner import DeviceScanner
from switchbot_actions.signals import state_changed
from switchbot_actions.store import StateStorage


@pytest.fixture
def mock_ble_scanner():
    """Provides a mock BLE scanner from the switchbot library."""
    scanner = AsyncMock()
    scanner.discover.side_effect = [
        {
            "DE:AD:BE:EF:44:44": MagicMock(
                address="DE:AD:BE:EF:44:44",
                data={"modelName": "WoHand", "data": {"isOn": True}},
            )
        },
        asyncio.CancelledError,  # To stop the loop after one iteration
    ]
    return scanner


@pytest.fixture
def mock_storage():
    """Provides a mock StateStorage."""
    return MagicMock(spec=StateStorage)


@pytest.fixture
def scanner(mock_ble_scanner, mock_storage):
    """Provides a DeviceScanner with mock dependencies."""
    return DeviceScanner(
        scanner=mock_ble_scanner, store=mock_storage, cycle=1, duration=1
    )


@pytest.mark.asyncio
async def test_scanner_start_scan_sends_signal(scanner, mock_ble_scanner):
    """Test that the scanner starts, processes an advertisement, and sends a signal."""
    received_signal = []

    def on_state_changed(sender, **kwargs):
        received_signal.append(kwargs)

    state_changed.connect(on_state_changed)

    with pytest.raises(asyncio.CancelledError):
        await scanner.start_scan()

    # Assert that discover was called
    mock_ble_scanner.discover.assert_called_with(scan_timeout=1)

    # Assert that a signal was sent
    assert len(received_signal) == 1
    signal_data = received_signal[0]
    new_state = signal_data["new_state"]
    assert new_state.address == "DE:AD:BE:EF:44:44"
    assert new_state.data["data"]["isOn"] is True

    state_changed.disconnect(on_state_changed)


@pytest.mark.asyncio
@patch("logging.Logger.error")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_scanner_error_handling(
    mock_sleep, mock_log_error, scanner, mock_ble_scanner
):
    """Test that the scanner handles BLE scan errors gracefully."""
    mock_ble_scanner.discover.side_effect = [
        Exception("BLE error"),
        asyncio.CancelledError,
    ]

    with pytest.raises(asyncio.CancelledError):
        await scanner.start_scan()

    mock_log_error.assert_called_once()
    assert "Error during BLE scan: BLE error." in mock_log_error.call_args[0][0]
    # In case of error, it should sleep for the full cycle time
    mock_sleep.assert_called_with(1)
