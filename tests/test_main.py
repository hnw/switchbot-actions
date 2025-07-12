# tests/test_main.py
import logging
from unittest.mock import AsyncMock, mock_open, patch

import pytest

from switchbot_exporter.main import load_config, main, setup_logging


@patch("logging.getLogger")
@patch("logging.basicConfig")
def test_setup_logging_debug_mode(mock_basic_config, mock_get_logger):
    """Test that --debug flag sets root to DEBUG and bleak to INFO."""
    setup_logging(config={}, debug=True)

    # Check basicConfig call for root logger
    mock_basic_config.assert_called_once()
    _, kwargs = mock_basic_config.call_args
    assert kwargs["level"] == logging.DEBUG

    # Check getLogger call for bleak
    mock_get_logger.assert_any_call("bleak")
    mock_get_logger.return_value.setLevel.assert_called_once_with(logging.INFO)


@patch("logging.getLogger")
@patch("logging.basicConfig")
def test_setup_logging_from_config_with_loggers(mock_basic_config, mock_get_logger):
    """Test that logging is configured from config file, including specific loggers."""
    config = {
        "logging": {
            "level": "WARNING",
            "format": "%(message)s",
            "loggers": {"bleak": "ERROR", "aiohttp": "CRITICAL"},
        }
    }
    setup_logging(config=config, debug=False)

    # Check basicConfig call for root logger
    mock_basic_config.assert_called_once()
    _, kwargs = mock_basic_config.call_args
    assert kwargs["level"] == logging.WARNING
    assert kwargs["format"] == "%(message)s"

    # Check getLogger calls for specific libraries
    mock_get_logger.assert_any_call("bleak")
    mock_get_logger.assert_any_call("aiohttp")
    mock_get_logger.return_value.setLevel.assert_any_call(logging.ERROR)
    mock_get_logger.return_value.setLevel.assert_any_call(logging.CRITICAL)


@patch("logging.basicConfig")
def test_setup_logging_from_config_no_loggers(mock_basic_config):
    """Test that logging is configured correctly when loggers section is missing."""
    config = {"logging": {"level": "INFO"}}
    setup_logging(config=config, debug=False)

    mock_basic_config.assert_called_once()
    _, kwargs = mock_basic_config.call_args
    assert kwargs["level"] == logging.INFO


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="prometheus_exporter:\n  port: 8888",
)
def test_load_config(mock_file):
    """Test loading a simple config."""
    config = load_config("dummy_path.yaml")
    assert config["prometheus_exporter"]["port"] == 8888


@patch("builtins.open", new_callable=mock_open)
def test_load_config_file_not_found(mock_file):
    """Test that the application returns a default config if file is not found."""
    mock_file.side_effect = FileNotFoundError
    config = load_config("non_existent.yaml")
    assert config == {}


@patch("builtins.open", new_callable=mock_open, read_data="invalid_yaml: [{")
def test_load_config_yaml_error(mock_file):
    """Test that the application exits on YAML parsing error."""
    with pytest.raises(SystemExit):
        load_config("invalid.yaml")


@patch("switchbot_exporter.main.setup_logging")
@patch("switchbot_exporter.main.DeviceScanner")
@patch("switchbot_exporter.main.PrometheusExporter")
@patch("switchbot_exporter.main.EventDispatcher")
@patch("switchbot_exporter.main.TimerHandler")
@patch("switchbot_exporter.main.load_config")
@patch("argparse.ArgumentParser")
@pytest.mark.asyncio
async def test_main_initialization_all_enabled(
    mock_arg_parser,
    mock_load_config,
    mock_timer_handler,
    mock_dispatcher,
    mock_exporter,
    mock_scanner,
    mock_setup_logging,
):
    """Test that main initializes all components when config is full."""
    # Mock argparse
    mock_args = mock_arg_parser.return_value.parse_args.return_value
    mock_args.config = "config.yaml"
    mock_args.debug = False

    mock_load_config.return_value = {
        "prometheus_exporter": {"enabled": True, "port": 9090, "target": {}},
        "actions": [{"name": "test_action"}],
        "timers": [{"name": "test_timer"}],
    }
    mock_scanner.return_value.start_scan = AsyncMock(side_effect=KeyboardInterrupt)
    mock_scanner.return_value.stop_scan = AsyncMock()

    await main()

    mock_load_config.assert_called_once_with("config.yaml")
    mock_setup_logging.assert_called_once_with(mock_load_config.return_value, False)
    mock_exporter.assert_called_once()
    mock_dispatcher.assert_called_once()
    mock_timer_handler.assert_called_once()
    mock_scanner.assert_called_once()
    mock_exporter.return_value.start_server.assert_called_once()
    mock_scanner.return_value.start_scan.assert_awaited_once()
