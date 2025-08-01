import logging
from unittest.mock import patch

from switchbot_actions.config import AppSettings, LoggingSettings
from switchbot_actions.logging import setup_logging


@patch("logging.getLogger")
@patch("logging.basicConfig")
def test_setup_logging_debug_mode(mock_basic_config, mock_get_logger):
    """Test that --debug flag sets root to DEBUG and bleak to INFO."""
    settings = AppSettings(debug=True)
    setup_logging(settings)

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
    settings = AppSettings(
        logging=LoggingSettings(
            level="WARNING",
            format="%(message)s",
            loggers={"bleak": "ERROR", "aiohttp": "CRITICAL"},
        )
    )
    setup_logging(settings)

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
    settings = AppSettings(logging=LoggingSettings(level="INFO"))
    setup_logging(settings)

    mock_basic_config.assert_called_once()
    _, kwargs = mock_basic_config.call_args
    assert kwargs["level"] == logging.INFO
