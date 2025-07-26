from unittest.mock import MagicMock, patch

import pytest

from switchbot_actions.app import Application, run_app
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
            await run_app(settings, mock_args)

    # Check that it exited with code 1
    assert e.value.code == 1
    # Check that the correct error was logged
    mock_logger_error.assert_called_once_with(
        "Scan duration (20s) cannot be longer than the scan cycle (10s)."
    )


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.info")
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.config.AppSettings.load_from_yaml")
@patch("switchbot_actions.exporter.start_http_server")
async def test_reload_settings_cli_args_are_kept(
    mock_start_http_server, mock_load_from_yaml, mock_logger_error, mock_logger_info
):
    """Test that CLI arguments are kept after reloading settings."""
    # Initial setup
    mock_args = MagicMock()
    mock_args.config = "config.yaml"
    mock_args.debug = True
    mock_args.scan_cycle = 20
    mock_args.scan_duration = 5
    mock_args.interface = 1
    mock_args.prometheus_exporter_enabled = None
    mock_args.prometheus_exporter_port = None
    mock_args.mqtt_host = None
    mock_args.mqtt_port = None
    mock_args.mqtt_username = None
    mock_args.mqtt_password = None
    mock_args.mqtt_reconnect_interval = None
    mock_args.log_level = None

    initial_config = {
        "scanner": {"cycle": 10, "duration": 3},
        "prometheus_exporter": {"enabled": True},
    }
    mock_load_from_yaml.return_value = initial_config
    settings = AppSettings.from_args(mock_args)

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(settings, mock_args)

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Check initial settings
    assert app.settings.scanner.cycle == 20
    assert app.settings.scanner.duration == 5
    assert app.settings.scanner.interface == 1
    assert app.settings.debug is True

    # Simulate reload with new config
    new_config = {
        "scanner": {"cycle": 30, "duration": 10},
        "prometheus_exporter": {"enabled": True},
    }
    mock_load_from_yaml.return_value = new_config
    app.reload_settings()

    # Assert that CLI args still override the new config
    assert app.settings.scanner.cycle == 20
    assert app.settings.scanner.duration == 5
    assert app.settings.scanner.interface == 1
    assert app.settings.debug is True
    assert app.settings.prometheus_exporter.enabled is True  # This should change
    mock_logger_error.assert_not_called()
    mock_logger_info.assert_any_call("Configuration reloaded successfully.")


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.config.AppSettings.load_from_yaml")
@patch("switchbot_actions.exporter.start_http_server")
async def test_reload_settings_with_invalid_config(
    mock_start_http_server, mock_load_from_yaml, mock_logger_error
):
    """Test that reloading with invalid config does not crash and logs an error."""
    mock_args = MagicMock()
    mock_args.config = "config.yaml"
    mock_args.debug = False
    mock_args.scan_cycle = None
    mock_args.scan_duration = None
    mock_args.interface = None
    mock_args.prometheus_exporter_enabled = None
    mock_args.prometheus_exporter_port = None
    mock_args.mqtt_host = None
    mock_args.mqtt_port = None
    mock_args.mqtt_username = None
    mock_args.mqtt_password = None
    mock_args.mqtt_reconnect_interval = None
    mock_args.log_level = None

    initial_config = {
        "scanner": {"cycle": 10, "duration": 3},
        "prometheus_exporter": {"enabled": True},
    }

    mock_load_from_yaml.return_value = initial_config
    settings = AppSettings.from_args(mock_args)

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(settings, mock_args)

    original_settings = app.settings

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Simulate failed reload
    mock_load_from_yaml.return_value = None
    app.reload_settings()

    # Assert that settings have not changed and an error was logged
    assert app.settings is original_settings
    mock_logger_error.assert_called_once_with(
        "Failed to parse new configuration, keeping the old one."
    )
