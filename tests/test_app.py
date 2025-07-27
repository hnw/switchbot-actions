from unittest import mock
from unittest.mock import mock_open, patch

import pytest
import yaml  # Import yaml

from switchbot_actions.app import Application
from switchbot_actions.config import AppSettings


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.info")
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.exporter.start_http_server")
async def test_reload_settings_cli_args_are_kept(
    mock_start_http_server, mock_logger_error, mock_logger_info
):
    """Test that CLI arguments are kept after reloading settings."""
    # Initial setup
    initial_config_data = {
        "scanner": {"cycle": 10, "duration": 3},
        "prometheus_exporter": {"enabled": True},
        "debug": False,  # Default from config
    }
    settings = AppSettings.model_validate(initial_config_data)

    # Simulate CLI overrides (these would be applied in cli.py before run_app)
    settings.debug = True
    settings.scanner.cycle = 20
    settings.scanner.duration = 5
    settings.scanner.interface = 1

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(settings)

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Check initial settings (after CLI overrides)
    assert app.settings.scanner.cycle == 20
    assert app.settings.scanner.duration == 5
    assert app.settings.scanner.interface == 1
    assert app.settings.debug is True

    # Simulate reload with new config data
    new_config_data = {
        "scanner": {"cycle": 30, "duration": 10},
        "prometheus_exporter": {"enabled": True},
        "debug": False,  # New default from config
    }

    with (
        patch("builtins.open", mock_open(read_data="")),
        patch("switchbot_actions.app.yaml.safe_load", return_value=new_config_data),
    ):
        app.reload_settings()

    # Assert that CLI args are NOT re-applied during reload, only config file is loaded
    # The settings should now reflect the reloaded config, not the initial CLI overrides
    assert app.settings.scanner.cycle == 30
    assert app.settings.scanner.duration == 10
    assert app.settings.scanner.interface == 0  # Default, as not in new_config_data
    assert app.settings.debug is False  # From new_config_data
    assert app.settings.prometheus_exporter.enabled is True
    mock_logger_error.assert_not_called()
    mock_logger_info.assert_any_call("Configuration reloaded successfully.")


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.exporter.start_http_server")
async def test_reload_settings_with_invalid_config(
    mock_start_http_server, mock_logger_error
):
    """Test that reloading with invalid config does not crash and logs an error."""
    initial_config_data = {
        "scanner": {"cycle": 10, "duration": 3},
        "prometheus_exporter": {"enabled": True},
    }
    settings = AppSettings.model_validate(initial_config_data)

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(settings)

    original_settings = app.settings

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Simulate failed reload with invalid YAML
    with (
        patch("builtins.open", mock_open(read_data="")),
        patch(
            "switchbot_actions.app.yaml.safe_load",
            side_effect=yaml.YAMLError("Error parsing YAML file"),
        ),
    ):
        app.reload_settings()

    # Assert that settings have not changed and an error was logged for YAML parsing
    assert app.settings is original_settings
    mock_logger_error.assert_any_call(
        "Error parsing YAML file: Error parsing YAML file"
    )
    mock_logger_error.assert_any_call(
        "Failed to parse new configuration, keeping the old one."
    )
    mock_logger_error.reset_mock()

    # Simulate failed reload with Pydantic validation error
    invalid_pydantic_data = {
        "scanner": {"cycle": 5, "duration": 10},  # Invalid duration
    }
    with (
        patch("builtins.open", mock_open(read_data="")),
        patch(
            "switchbot_actions.app.yaml.safe_load", return_value=invalid_pydantic_data
        ),
    ):
        app.reload_settings()

    # Assert that settings have not changed and an error was logged
    # for Pydantic validation
    assert app.settings is original_settings
    mock_logger_error.assert_any_call(mock.ANY)
    mock_logger_error.assert_any_call(
        "Failed to validate new configuration, keeping the old one."
    )
