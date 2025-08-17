# tests/test_scanner.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.config import ScannerSettings
from switchbot_actions.scanner import SwitchbotScanner
from switchbot_actions.signals import switchbot_advertisement_received
from switchbot_actions.store import StateStore


@pytest.fixture
def mock_ble_scanner(mock_switchbot_advertisement):
    """Provides a mock BLE scanner from the switchbot library."""
    scanner = AsyncMock()

    advertisement = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:44:44",
        data={"modelName": "WoHand", "data": {"isOn": True}},
    )

    scanner.discover.side_effect = [
        {"DE:AD:BE:EF:44:44": advertisement},
        asyncio.CancelledError,  # To stop the loop after one iteration
    ]

    return scanner


@pytest.fixture
def mock_storage():
    """Provides a mock StateStore."""
    return MagicMock(spec=StateStore)


@pytest.fixture
def scanner_settings():
    """Provides mock ScannerSettings."""
    return ScannerSettings(interface=0, duration=1, wait=1)


@pytest.fixture
def scanner(mock_ble_scanner, scanner_settings):
    """Provides a SwitchbotScanner with mock dependencies."""
    return SwitchbotScanner(settings=scanner_settings, scanner=mock_ble_scanner)


@pytest.mark.asyncio
async def test_scanner_start_and_stop_succeeds(scanner, mock_ble_scanner):
    """Test that the scanner starts, sends a signal, and stops gracefully."""
    received_signal = []

    def on_switchbot_advertisement_received(sender, **kwargs):
        received_signal.append(kwargs)

    switchbot_advertisement_received.connect(on_switchbot_advertisement_received)

    # Start the scanner
    await scanner.start()
    assert scanner.task is not None

    # Give the background task a moment to run one loop
    await asyncio.sleep(0.1)

    # Assert that discover was called
    mock_ble_scanner.discover.assert_called_with(scan_timeout=1)

    # Assert that a signal was sent
    assert len(received_signal) == 1
    signal_data = received_signal[0]
    new_state = signal_data["new_state"]
    assert new_state.address == "DE:AD:BE:EF:44:44"

    # Stop the scanner and ensure it logs the cancellation correctly
    with patch("logging.Logger.info") as mock_logger_info:
        await scanner.stop()
        mock_logger_info.assert_any_call("Scanner task successfully cancelled.")

    switchbot_advertisement_received.disconnect(on_switchbot_advertisement_received)


@pytest.mark.parametrize(
    "error_exception, expected_exc_info",
    [
        (Exception("Some other error"), True),  # Unknown error
        (Exception("Bluetooth device is turned off"), False),  # Known error
    ],
)
@pytest.mark.asyncio
@patch("logging.Logger.error")
async def test_scanner_error_handling(
    mock_log_error,
    scanner,
    mock_ble_scanner,
    error_exception,
    expected_exc_info,
):
    """
    Test that the scanner's background task handles BLE errors gracefully.
    """
    # Configure the mock scanner to raise the test exception
    mock_ble_scanner.discover.side_effect = error_exception

    # Start the scanner, which starts the _scan_loop in the background
    await scanner.start()
    assert scanner.task is not None

    # Give the background task a moment to run, encounter the error, and log it.
    await asyncio.sleep(0.1)

    # Verify that the error was logged correctly
    mock_log_error.assert_called_once()
    args, kwargs = mock_log_error.call_args

    assert str(error_exception) in args[0]
    if expected_exc_info:
        assert kwargs.get("exc_info") is True
    else:
        assert not kwargs.get("exc_info")

    # Clean up by stopping the scanner
    await scanner.stop()


@pytest.mark.parametrize(
    "exception, expected_message_part, expected_is_known_error",
    [
        (
            Exception("Bluetooth device is turned off"),
            "Please ensure your Bluetooth adapter is turned on.",
            True,
        ),
        (
            Exception("BLE is not authorized"),
            "Please check your OS's privacy settings for Bluetooth.",
            True,
        ),
        (
            Exception("Permission denied"),
            "Check if the program has Bluetooth permissions",
            True,
        ),
        (Exception("No such device"), "Bluetooth device not found.", True),
        (
            Exception("Some other error"),
            "This might be due to adapter issues, permissions, "
            "or other environmental factors.",
            False,
        ),
    ],
)
def test_format_ble_error_message(
    exception, expected_message_part, expected_is_known_error
):
    """
    Test that _format_ble_error_message generates correct messages and known error flag.
    """
    client = SwitchbotScanner(MagicMock(), MagicMock())
    message, is_known_error = client._format_ble_error_message(exception)
    assert expected_message_part in message
    assert is_known_error == expected_is_known_error


@pytest.mark.asyncio
async def test_scanner_already_running_warning(scanner):
    """Test that starting an already running scanner logs a warning."""
    scanner._running = True  # Manually set state for test
    with patch("logging.Logger.warning") as mock_log_warning:
        await scanner.start()
        # The generic message from BaseComponent is expected
        mock_log_warning.assert_called_once_with("SwitchbotScanner is already running.")


@pytest.mark.asyncio
async def test_scanner_not_running_warning(scanner):
    """Test that stopping a not running scanner logs a debug message."""
    scanner._running = False  # Manually set state for test
    with patch("logging.Logger.debug") as mock_log_debug:
        await scanner.stop()
        # The generic message from BaseComponent is expected at DEBUG level
        mock_log_debug.assert_called_once_with("SwitchbotScanner is not running.")


@pytest.mark.asyncio
async def test_switchbot_client_initializes_scanner_internally(scanner_settings):
    """
    Test that SwitchbotScanner initializes GetSwitchbotDevices internally
    when no scanner is provided.
    """
    with patch(
        "switchbot_actions.scanner.GetSwitchbotDevices"
    ) as MockGetSwitchbotDevices:
        # Instantiate SwitchbotScanner without providing a scanner mock
        client = SwitchbotScanner(settings=scanner_settings)

        # Assert that GetSwitchbotDevices was called with the correct interface
        MockGetSwitchbotDevices.assert_called_once_with(
            interface=scanner_settings.interface
        )

        # Verify that the internal _scanner attribute is set to the mock instance
        assert client._scanner == MockGetSwitchbotDevices.return_value

        # Configure mock discover to return empty dict then raise CancelledError
        MockGetSwitchbotDevices.return_value.discover.side_effect = [
            {},
            asyncio.CancelledError,
        ]

        # Ensure start/stop can still be called
        await client.start()
        # The loop should stop after one iteration due to the mock's side_effect
        # Wait a bit to ensure the task has been processed
        await asyncio.sleep(0.1)

        MockGetSwitchbotDevices.return_value.discover.assert_called()
        await client.stop()
        # discover is called once per loop iteration, so it should still be 1 after stop
        MockGetSwitchbotDevices.return_value.discover.assert_called()


# --- Added Tests for Reload Logic ---


def test_require_restart_on_interface_change(scanner_settings):
    """Tests that _require_restart returns True when the interface changes."""
    scanner = SwitchbotScanner(settings=scanner_settings)
    new_settings = scanner_settings.model_copy()
    new_settings.interface = 99  # A different interface

    assert scanner._require_restart(new_settings) is True


@pytest.mark.parametrize("setting_to_change", ["duration", "wait"])
def test_no_restart_on_timing_settings_change(scanner_settings, setting_to_change):
    """
    Tests that _require_restart returns False when timing settings like
    duration or wait are changed.
    """
    scanner = SwitchbotScanner(settings=scanner_settings)
    new_settings = scanner_settings.model_copy()

    # Change a non-critical setting
    setattr(new_settings, setting_to_change, 99)

    assert scanner._require_restart(new_settings) is False
