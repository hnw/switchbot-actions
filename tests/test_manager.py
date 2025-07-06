# tests/test_manager.py
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from switchbot_exporter.manager import SwitchbotManager
from switchbot_exporter.signals import advertisement_received

@pytest.fixture
def mock_scanner():
    """Provides a mock scanner."""
    scanner = AsyncMock()
    # Configure the mock to raise an exception after the first call
    scanner.discover.side_effect = [
        {"DE:AD:BE:EF:44:44": MagicMock(
            address="DE:AD:BE:EF:44:44",
            data={'modelName': 'WoHand', 'data': {'isOn': True}}
        )},
        asyncio.CancelledError,
    ]
    return scanner

@pytest.fixture
def manager(mock_scanner):
    """Provides a SwitchbotManager with a mock scanner."""
    # Use a short interval to speed up the test
    return SwitchbotManager(scanner=mock_scanner, scan_interval=0.01)

@pytest.mark.asyncio
async def test_manager_start_scan(manager, mock_scanner):
    """Test that the manager starts scanning and processes one advertisement."""
    received_signal = []
    def on_advertisement(sender, **kwargs):
        received_signal.append(kwargs.get('device_data'))

    advertisement_received.connect(on_advertisement)

    # The loop will be terminated by the CancelledError from the mock
    with pytest.raises(asyncio.CancelledError):
        await manager.start_scan()

    # Check that discover was called at least once
    mock_scanner.discover.assert_called()

    # Check that the signal was received correctly
    assert len(received_signal) == 1
    assert received_signal[0].address == "DE:AD:BE:EF:44:44"
    assert received_signal[0].data['data']['isOn'] is True

    advertisement_received.disconnect(on_advertisement)

@pytest.mark.asyncio
@patch('logging.Logger.error')
@patch('asyncio.sleep', new_callable=AsyncMock)
async def test_manager_scan_error_handling(mock_sleep, mock_log_error, manager, mock_scanner):
    """Test that the manager handles scan errors gracefully and logs them."""
    mock_scanner.discover.side_effect = [Exception("Bluetooth device is turned off"), asyncio.CancelledError]

    with pytest.raises(asyncio.CancelledError):
        await manager.start_scan()

    mock_log_error.assert_called_once_with(
        "Error during BLE scan: Bluetooth device is turned off. Please ensure your Bluetooth adapter is turned on.", exc_info=True
    )
    mock_sleep.assert_called_once() # Should sleep after an error before retrying
