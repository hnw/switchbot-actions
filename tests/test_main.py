# tests/test_main.py
import logging
from unittest.mock import ANY, AsyncMock, mock_open, patch

import pytest

from switchbot_actions.main import load_config, main, setup_logging


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


@patch("switchbot_actions.main.setup_logging")
@patch("switchbot_actions.main.GetSwitchbotDevices")
@patch("switchbot_actions.main.DeviceScanner")
@patch("switchbot_actions.main.PrometheusExporter")
@patch("switchbot_actions.main.EventDispatcher")
@patch("switchbot_actions.main.TimerHandler")
@patch("switchbot_actions.main.load_config")
@patch("argparse.ArgumentParser")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cli_args, config_file, expected",
    [
        # Priority 1: Command-line arguments
        (
            {"scan_cycle": 10, "scan_duration": 2, "interface": "hci1"},
            {"scanner": {"cycle": 99, "duration": 9, "interface": "hci9"}},
            {"cycle": 10, "duration": 2, "interface": "hci1"},
        ),
        # Priority 2: Config file
        (
            {"scan_cycle": None, "scan_duration": None, "interface": None},
            {"scanner": {"cycle": 20, "duration": 8, "interface": "hci2"}},
            {"cycle": 20, "duration": 8, "interface": "hci2"},
        ),
        # Priority 3: Default values
        (
            {"scan_cycle": None, "scan_duration": None, "interface": None},
            {},
            {"cycle": 10, "duration": 3, "interface": "hci0"},
        ),
    ],
)
async def test_main_scanner_config_priority(
    mock_arg_parser,
    mock_load_config,
    mock_timer_handler,
    mock_dispatcher,
    mock_exporter,
    mock_scanner,
    mock_get_switchbot_devices,
    mock_setup_logging,
    cli_args,
    config_file,
    expected,
):
    """Test scanner config priority: CLI > config > default."""
    # Mock argparse to return specific values
    mock_args = mock_arg_parser.return_value.parse_args.return_value
    mock_args.config = "config.yaml"
    mock_args.debug = False
    mock_args.scan_cycle = cli_args["scan_cycle"]
    mock_args.scan_duration = cli_args["scan_duration"]
    mock_args.interface = cli_args["interface"]

    mock_load_config.return_value = config_file

    # Mock async methods to allow the main loop to run once and exit
    mock_scanner.return_value.start_scan = AsyncMock(side_effect=KeyboardInterrupt)
    mock_scanner.return_value.stop_scan = AsyncMock()

    # Mock other components
    mock_load_config.return_value.setdefault("prometheus_exporter", {})
    mock_load_config.return_value.setdefault("actions", [])
    mock_load_config.return_value.setdefault("timers", [])

    await main()

    # Verify scanner components were initialized with expected values
    mock_get_switchbot_devices.assert_called_with(interface=expected["interface"])
    mock_scanner.assert_called_with(
        scanner=mock_get_switchbot_devices.return_value,
        store=ANY,
        cycle=expected["cycle"],
        duration=expected["duration"],
    )


@patch("switchbot_actions.main.logger.error")
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

    # Patch load_config to return an empty config
    with patch("switchbot_actions.main.load_config", return_value={}):
        with pytest.raises(SystemExit) as e:
            await main()

    # Check that it exited with code 1
    assert e.value.code == 1
    # Check that the correct error was logged
    mock_logger_error.assert_called_once_with(
        "Scan duration (20s) cannot be longer than the scan cycle (10s)."
    )
