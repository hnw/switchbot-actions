from unittest.mock import patch

import pytest

from switchbot_actions.app import run_app
from switchbot_actions.config import AppSettings


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
