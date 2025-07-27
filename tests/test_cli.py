import io
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.cli import cli_main
from switchbot_actions.config import (
    AppSettings,
    ScannerSettings,
)


@patch("sys.argv", ["cli_main"])
@patch("switchbot_actions.cli.run_app", new_callable=MagicMock)
@patch("switchbot_actions.cli.asyncio.run")
@patch("switchbot_actions.cli.logger")
@patch("switchbot_actions.cli.AppSettings.model_validate")
def test_cli_main_keyboard_interrupt(
    mock_model_validate, mock_logger, mock_asyncio_run, mock_run_app
):
    """Test that cli_main handles KeyboardInterrupt and exits gracefully."""
    mock_model_validate.return_value = AppSettings(
        scanner=ScannerSettings(cycle=10, duration=3)
    )

    mock_asyncio_run.side_effect = KeyboardInterrupt

    with pytest.raises(SystemExit) as e:
        cli_main()

    assert e.value.code == 0
    mock_logger.info.assert_called_once_with("Application terminated by user.")


@patch("sys.argv", ["cli_main", "--config", "tests/fixtures/invalid_config.yaml"])
@patch("switchbot_actions.cli.format_validation_error")
def test_cli_main_invalid_config_missing_field(mock_format_validation_error, tmp_path):
    """Test that cli_main handles a missing field error and exits."""
    invalid_config_content = """
automations:
  - name: "Turn off Lights if No Motion for 3 Minutes"
    then:
      - type: shell_command
        command: "echo 'hello'"
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    mock_format_validation_error.return_value = "Mocked Validation Error Output"

    f = io.StringIO()
    with redirect_stderr(f):
        with pytest.raises(SystemExit) as e:
            with patch("sys.argv", ["cli_main", "--config", str(config_file)]):
                cli_main()

    actual_output = f.getvalue()

    assert e.value.code == 1
    assert actual_output.strip() == "Mocked Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], Exception)  # Check if it's a ValidationError instance
    assert args[1] == config_file
    assert isinstance(args[2], dict)  # Check if it's the config_data


@patch("sys.argv", ["cli_main", "--config", "tests/fixtures/invalid_config.yaml"])
@patch("switchbot_actions.cli.format_validation_error")
def test_cli_main_invalid_config_enum(mock_format_validation_error, tmp_path):
    """Test that cli_main handles an enum error and exits."""
    invalid_config_content = """
logging:
  level: "DETAIL"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    mock_format_validation_error.return_value = "Mocked Enum Validation Error Output"

    f = io.StringIO()
    with redirect_stderr(f):
        with pytest.raises(SystemExit) as e:
            with patch("sys.argv", ["cli_main", "--config", str(config_file)]):
                cli_main()

    actual_output = f.getvalue()

    assert e.value.code == 1
    assert actual_output.strip() == "Mocked Enum Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], Exception)
    assert args[1] == config_file
    assert isinstance(args[2], dict)


@patch("sys.argv", ["cli_main", "--config", "tests/fixtures/invalid_config.yaml"])
@patch("switchbot_actions.cli.format_validation_error")
def test_cli_main_invalid_config_tag(mock_format_validation_error, tmp_path):
    """Test that cli_main handles an enum error and exits."""
    invalid_config_content = """
automations:
  - if:
      source: mqtt
    then:
      type: mqtt-publish
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    mock_format_validation_error.return_value = "Mocked Tag Validation Error Output"

    f = io.StringIO()
    with redirect_stderr(f):
        with pytest.raises(SystemExit) as e:
            with patch("sys.argv", ["cli_main", "--config", str(config_file)]):
                cli_main()

    actual_output = f.getvalue()

    assert e.value.code == 1
    assert actual_output.strip() == "Mocked Tag Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], Exception)
    assert args[1] == config_file
    assert isinstance(args[2], dict)
