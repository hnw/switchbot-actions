# tests/test_manager.py
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
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
            data={'modelName': 'Bot', 'data': {'isOn': True}}
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
