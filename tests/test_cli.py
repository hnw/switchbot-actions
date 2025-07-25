from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.cli import cli_main


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
def test_cli_main_keyboard_interrupt(mock_logger, mock_asyncio_run, mock_run_app):
    """Test that cli_main handles KeyboardInterrupt and exits gracefully."""
    mock_asyncio_run.side_effect = KeyboardInterrupt

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_logger.info.assert_called_once_with("Application terminated by user.")
