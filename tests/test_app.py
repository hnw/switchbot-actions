from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from switchbot_actions.app import run_app
from switchbot_actions.config import AppSettings


@patch("switchbot_actions.app.AutomationHandler", new_callable=MagicMock)
@patch("switchbot_actions.app.PrometheusExporter", new_callable=MagicMock)
@patch("switchbot_actions.app.DeviceScanner", new_callable=MagicMock)
@patch("switchbot_actions.app.GetSwitchbotDevices", new_callable=MagicMock)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cli_args, config_file, expected",
    [
        # Priority 1: Command-line arguments
        (
            {"scan_cycle": 10, "scan_duration": 2, "interface": 1},
            {"scanner": {"cycle": 99, "duration": 9, "interface": 9}},
            {"cycle": 10, "duration": 2, "interface": 1},
        ),
        # Priority 2: Config file
        (
            {"scan_cycle": None, "scan_duration": None, "interface": None},
            {"scanner": {"cycle": 20, "duration": 8, "interface": 2}},
            {"cycle": 20, "duration": 8, "interface": 2},
        ),
        # Priority 3: Default values
        (
            {"scan_cycle": None, "scan_duration": None, "interface": None},
            {},
            {"cycle": 10, "duration": 3, "interface": 0},
        ),
    ],
)
async def test_main_scanner_config_priority(
    mock_get_switchbot_devices,
    mock_device_scanner,  # Renamed mock_scanner to mock_device_scanner for clarity
    mock_prometheus_exporter,  # Renamed mock_exporter for clarity
    mock_automation_handler,
    cli_args,
    config_file,
    expected,
):
    """Test scanner config priority: CLI > config > default."""
    # Create a mock args object for AppSettings.from_args
    mock_args = MagicMock()
    mock_args.config = "config.yaml"
    mock_args.debug = False
    mock_args.scan_cycle = cli_args["scan_cycle"]
    mock_args.scan_duration = cli_args["scan_duration"]
    mock_args.interface = cli_args["interface"]

    # Mock AppSettings.load_from_yaml to return the config_file data
    with patch(
        "switchbot_actions.config.AppSettings.load_from_yaml",
        return_value=config_file,
    ):
        settings = AppSettings.from_args(mock_args)

    # Ensure automations are present for the AutomationHandler to be initialized
    settings.automations = [{"name": "Test Automation", "if": {}, "then": []}]

    # Mock async methods to allow the main loop to run once and exit
    mock_device_scanner_instance = MagicMock()
    mock_device_scanner_instance.start_scan = AsyncMock(side_effect=KeyboardInterrupt)
    mock_device_scanner_instance.stop_scan = AsyncMock()
    mock_device_scanner.return_value = mock_device_scanner_instance

    await run_app(settings)

    # Verify scanner components were initialized with expected values
    mock_get_switchbot_devices.assert_called_once_with(interface=expected["interface"])
    mock_device_scanner.assert_called_once_with(
        scanner=mock_get_switchbot_devices.return_value,
        store=ANY,
        cycle=expected["cycle"],
        duration=expected["duration"],
    )


@patch("switchbot_actions.app.logger.error")
@patch("argparse.ArgumentParser")
@pytest.mark.asyncio
async def test_main_invalid_scanner_config_exits(mock_arg_parser, mock_logger_error):
    """Test that the application exits if scan_duration > scan_cycle."""
    # Mock argparse to return invalid values
    mock_args = mock_arg_parser.return_value.parse_args.return_value
    mock_args.config = "config.yaml"
    mock_args.debug = False
    mock_args.scan_cycle = 10
    mock_args.scan_duration = 20  # Invalid: duration > cycle
    mock_args.interface = None  # use default

    # Patch AppSettings.load_from_yaml to return an empty config
    with patch("switchbot_actions.config.AppSettings.load_from_yaml", return_value={}):
        settings = AppSettings.from_args(mock_args)
        with pytest.raises(SystemExit) as e:
            await run_app(settings)

    # Check that it exited with code 1
    assert e.value.code == 1
    # Check that the correct error was logged
    mock_logger_error.assert_called_once_with(
        "Scan duration (20s) cannot be longer than the scan cycle (10s)."
    )
