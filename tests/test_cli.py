from unittest.mock import MagicMock, call, patch

import pytest

from switchbot_actions.cli import cli_main
from switchbot_actions.error import ConfigError


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.load_settings_from_cli")
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
def test_cli_main_keyboard_interrupt(
    mock_logger,
    mock_asyncio_run,
    mock_load_settings,
    mock_run_app,
):
    """Test that cli_main handles KeyboardInterrupt and exits gracefully."""
    mock_asyncio_run.side_effect = KeyboardInterrupt

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_logger.info.assert_called_once_with("Application terminated by user.")
    mock_asyncio_run.assert_called_once()
    mock_run_app.assert_called_once()


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.load_settings_from_cli")
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
@patch("sys.stderr", new_callable=MagicMock)
def test_cli_main_config_error(
    mock_stderr,
    mock_logger,
    mock_asyncio_run,
    mock_load_settings,
    mock_run_app,
):
    """Test that cli_main handles ConfigError during startup and exits with error."""
    mock_load_settings.side_effect = ConfigError("Test configuration error")

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 1
    mock_stderr.write.assert_has_calls(
        [call("Error loading configuration: Test configuration error"), call("\n")]
    )
    mock_load_settings.assert_called_once()
    mock_asyncio_run.assert_not_called()
    mock_run_app.assert_not_called()


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.load_settings_from_cli")
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
def test_cli_main_happy_path(
    mock_logger,
    mock_asyncio_run,
    mock_load_settings,
    mock_run_app,
):
    """Test the successful execution of cli_main."""
    cli_main()

    mock_load_settings.assert_called_once()
    mock_asyncio_run.assert_called_once()
    mock_run_app.assert_called_once()


@patch("sys.argv", ["cli_main", "--check"])
@patch("builtins.print")
@patch("switchbot_actions.cli.run_app")
@patch("switchbot_actions.cli.load_settings_from_cli")
@patch("switchbot_actions.cli.asyncio.run")
def test_cli_main_check_valid_config(
    mock_asyncio_run, mock_load_settings, mock_run_app, mock_print
):
    """Test --check with a valid config exits successfully and does not run the app."""
    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_load_settings.assert_called_once()
    mock_print.assert_called_once_with("Configuration is valid.")
    mock_run_app.assert_not_called()
    mock_asyncio_run.assert_not_called()


@patch("sys.argv", ["cli_main", "--check"])
@patch("sys.stderr", new_callable=MagicMock)
@patch("switchbot_actions.cli.run_app")
@patch("switchbot_actions.cli.load_settings_from_cli")
@patch("switchbot_actions.cli.asyncio.run")
def test_cli_main_check_invalid_config(
    mock_asyncio_run, mock_load_settings, mock_run_app, mock_stderr
):
    """Test --check with an invalid config exits with an error."""
    mock_load_settings.side_effect = ConfigError("Invalid configuration")

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 1
    mock_load_settings.assert_called_once()
    mock_stderr.write.assert_has_calls(
        [call("Error loading configuration: Invalid configuration"), call("\n")]
    )
    mock_run_app.assert_not_called()
    mock_asyncio_run.assert_not_called()


@patch("sys.argv", ["cli_main", "--version"])
@patch("sys.stdout", new_callable=MagicMock)
@patch("switchbot_actions.cli.version")
def test_cli_main_version_option(
    mock_version,
    mock_stdout,
):
    """Test that --version option displays the correct version and exits."""
    mock_version.return_value = "1.2.3"

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_stdout.write.assert_called_once_with("cli_main 1.2.3\n")
    mock_version.assert_called_once_with("switchbot-actions")
