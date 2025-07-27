from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.cli import cli_main
from switchbot_actions.config import (  # Import necessary models
    AppSettings,
    ScannerSettings,
)


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
@patch("switchbot_actions.cli.AppSettings.model_validate")  # Mock model_validate
def test_cli_main_keyboard_interrupt(
    mock_model_validate, mock_logger, mock_asyncio_run, mock_run_app
):
    """Test that cli_main handles KeyboardInterrupt and exits gracefully."""
    # Configure mock_parse_obj to return a valid AppSettings instance
    mock_model_validate.return_value = AppSettings(
        scanner=ScannerSettings(cycle=10, duration=3)  # Provide valid default values
    )

    mock_asyncio_run.side_effect = KeyboardInterrupt

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_logger.info.assert_called_once_with("Application terminated by user.")
