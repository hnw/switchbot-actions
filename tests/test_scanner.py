# tests/test_scanner.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.scanner import DeviceScanner
from switchbot_actions.signals import advertisement_received
from switchbot_actions.store import DeviceStateStore


@pytest.fixture
def mock_scanner():
    """Provides a mock BLE scanner."""
    scanner = AsyncMock()
    scanner.discover.side_effect = [
        {
            "DE:AD:BE:EF:44:44": MagicMock(
                address="DE:AD:BE:EF:44:44", data={"modelName": "WoHand", "isOn": True}
            )
        },
        asyncio.CancelledError,
    ]
    return scanner


@pytest.fixture
def mock_store():
    """Provides a mock DeviceStateStore."""
    store = MagicMock(spec=DeviceStateStore)
    store.get_state.return_value = None  # Assume no previous state
    return store


@pytest.fixture
def scanner(mock_scanner, mock_store):
    """Provides a DeviceScanner with mock dependencies."""
    return DeviceScanner(scanner=mock_scanner, store=mock_store, cycle=1, duration=0.5)


@pytest.mark.asyncio
async def test_scanner_start_scan(scanner, mock_scanner, mock_store):
    """Test that the scanner starts, processes an advertisement, and sends a signal."""
    received_signal = []

    def on_advertisement(sender, **kwargs):
        received_signal.append(kwargs)

    advertisement_received.connect(on_advertisement)

    with pytest.raises(asyncio.CancelledError):
        await scanner.start_scan()

    mock_scanner.discover.assert_called_with(scan_timeout=0.5)
    mock_store.get_state.assert_called_with("DE:AD:BE:EF:44:44")

    assert len(received_signal) == 1
    signal_data = received_signal[0]
    assert signal_data["new_data"].address == "DE:AD:BE:EF:44:44"
    assert signal_data["new_data"].data["isOn"] is True
    assert signal_data["old_data"] is None

    advertisement_received.disconnect(on_advertisement)


@pytest.mark.asyncio
@patch("logging.Logger.error")
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_scanner_error_handling(
    mock_sleep, mock_log_error, scanner, mock_scanner
):
    """Test that the scanner handles BLE scan errors gracefully."""
    mock_scanner.discover.side_effect = [Exception("BLE error"), asyncio.CancelledError]

    with pytest.raises(asyncio.CancelledError):
        await scanner.start_scan()

    mock_log_error.assert_called_once()
    assert "Error during BLE scan: BLE error." in mock_log_error.call_args[0][0]
    # In case of error, it should sleep for the full cycle time
    mock_sleep.assert_called_with(1)
