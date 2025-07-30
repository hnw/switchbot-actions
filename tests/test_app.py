import argparse
import asyncio
import signal
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from switchbot_actions.app import Application, run_app
from switchbot_actions.config import (
    AppSettings,
    MqttSettings,
    PrometheusExporterSettings,
    ScannerSettings,
)
from switchbot_actions.signals import publish_mqtt_message_request


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.info")
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.exporter.start_http_server")
@patch("switchbot_actions.app.load_settings_from_cli")
async def test_reload_settings_cli_args_are_kept(
    mock_load_settings_from_cli,
    mock_start_http_server,
    mock_logger_error,
    mock_logger_info,
):
    """Test that reloading settings correctly applies new settings
    from config_loader."""
    # Initial setup: Simulate settings loaded from CLI with some overrides
    initial_settings = AppSettings(
        scanner=ScannerSettings(cycle=20, duration=5, interface=1),
        prometheus_exporter=PrometheusExporterSettings(enabled=True, port=8000),
        debug=True,
    )
    # Mock load_settings_from_cli to return the initial settings for the first call
    mock_load_settings_from_cli.return_value = initial_settings

    # Create a dummy args object for Application constructor
    dummy_args = argparse.Namespace(config="/path/to/config.yaml")

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(initial_settings, dummy_args)

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Check initial settings
    assert app.settings is initial_settings
    assert app.settings.scanner.cycle == 20
    assert app.settings.scanner.duration == 5
    assert app.settings.scanner.interface == 1
    assert app.settings.debug is True

    # Simulate reload: Mock load_settings_from_cli to return new settings
    reloaded_settings = AppSettings(
        scanner=ScannerSettings(cycle=30, duration=10, interface=0),
        prometheus_exporter=PrometheusExporterSettings(enabled=True, port=8000),
        debug=False,
    )
    mock_load_settings_from_cli.return_value = reloaded_settings

    app.reload_settings()

    # Assert that load_settings_from_cli was called with the correct args
    mock_load_settings_from_cli.assert_called_once_with(dummy_args)

    # Assert that app.settings has been updated to the reloaded_settings object
    assert app.settings is reloaded_settings
    assert app.settings.scanner.cycle == 30
    assert app.settings.scanner.duration == 10
    assert app.settings.scanner.interface == 0
    assert app.settings.debug is False
    assert app.settings.prometheus_exporter.enabled is True

    mock_logger_error.assert_not_called()
    mock_logger_info.assert_any_call("Configuration reloaded successfully.")


@pytest.mark.asyncio
@patch("switchbot_actions.app.MqttClient")
@patch("switchbot_actions.app.GetSwitchbotDevices")
async def test_mqtt_publish_action_via_signal(
    mock_get_switchbot_devices, mock_mqtt_client_class
):
    """Test that mqtt_publish action is correctly executed via signal."""
    # Mock MqttClient instance
    mock_mqtt_client_instance = mock_mqtt_client_class.return_value
    mock_mqtt_client_instance.publish = AsyncMock()

    # Initial setup: MQTT enabled
    initial_settings = AppSettings(mqtt=MqttSettings(host="localhost", port=1883))

    dummy_args = argparse.Namespace(config="/path/to/config.yaml")

    app = Application(initial_settings, dummy_args)

    # Ensure MQTT client is initialized and connected to the signal
    assert app.mqtt_client is mock_mqtt_client_instance
    mock_mqtt_client_class.assert_called_once()

    # Emit the signal
    topic = "test/topic"
    payload = "test_payload"
    qos = 1
    retain = True
    publish_mqtt_message_request.send(
        app, topic=topic, payload=payload, qos=qos, retain=retain
    )

    # Allow the asyncio task to run
    await asyncio.sleep(0.01)

    # Assert that MqttClient.publish was called with the correct arguments
    mock_mqtt_client_instance.publish.assert_called_once_with(
        topic=topic, payload=payload, qos=qos, retain=retain
    )


@pytest.mark.asyncio
@patch("switchbot_actions.app.MqttClient")
@patch("switchbot_actions.app.SwitchbotClient")
@patch("switchbot_actions.app.GetSwitchbotDevices")
async def test_application_start_and_stop_with_mqtt(
    mock_get_switchbot_devices,
    mock_switchbot_client_class,
    mock_mqtt_client_class,
):
    """Test that the application starts and stops correctly with MQTT enabled."""
    mock_mqtt_client_instance = mock_mqtt_client_class.return_value
    mock_mqtt_client_instance.run = AsyncMock()
    mock_switchbot_client_instance = mock_switchbot_client_class.return_value
    mock_switchbot_client_instance.start_scan = AsyncMock()
    mock_switchbot_client_instance.stop_scan = Mock()

    initial_settings = AppSettings(mqtt=MqttSettings(host="localhost", port=1883))
    dummy_args = argparse.Namespace(config="/path/to/config.yaml")

    app = Application(initial_settings, dummy_args)

    # Start the application
    asyncio.create_task(app.start())
    await asyncio.sleep(0.01)  # Allow tasks to start

    mock_mqtt_client_instance.run.assert_called_once()
    mock_switchbot_client_instance.start_scan.assert_called_once()

    # Stop the application
    await app.stop()

    mock_switchbot_client_instance.stop_scan.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.MqttClient")
@patch("switchbot_actions.app.GetSwitchbotDevices")
@patch("switchbot_actions.signals.publish_mqtt_message_request.disconnect")
async def test_mqtt_client_disconnects_on_reload(
    mock_disconnect_signal, mock_get_switchbot_devices, mock_mqtt_client_class
):
    """
    Test that the MQTT client disconnects when settings are reloaded
    and MQTT is disabled.
    """
    mock_mqtt_client_instance = mock_mqtt_client_class.return_value
    mock_mqtt_client_instance.disconnect = AsyncMock()

    # Initial setup: MQTT enabled
    initial_settings = AppSettings(mqtt=MqttSettings(host="localhost", port=1883))
    dummy_args = argparse.Namespace(config="/path/to/config.yaml")

    app = Application(initial_settings, dummy_args)

    # Ensure MQTT client is initialized
    assert app.mqtt_client is mock_mqtt_client_instance
    mock_mqtt_client_class.assert_called_once()

    # Simulate reload: MQTT disabled
    reloaded_settings = AppSettings()
    with patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings:
        mock_load_settings.return_value = reloaded_settings
        app.reload_settings()

    # Assert that the MQTT client was disconnected
    mock_disconnect_signal.assert_called_once_with(app._handle_mqtt_publish)
    assert app.mqtt_client is None


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
@patch("switchbot_actions.app.logger.info")
@patch("switchbot_actions.app.logger.error")
async def test_run_app_handles_keyboard_interrupt(
    mock_logger_error,
    mock_logger_info,
    mock_get_running_loop,
    mock_application_class,
):
    """Test that run_app handles KeyboardInterrupt gracefully."""
    mock_app_instance = mock_application_class.return_value
    mock_app_instance.start = AsyncMock(side_effect=KeyboardInterrupt)
    mock_app_instance.stop = AsyncMock()

    mock_loop = Mock()
    mock_get_running_loop.return_value = mock_loop

    await run_app(AppSettings(), argparse.Namespace())

    mock_loop.add_signal_handler.assert_called_once_with(
        signal.SIGHUP, mock_app_instance.reload_settings
    )
    mock_app_instance.start.assert_called_once()
    mock_logger_info.assert_any_call("Keyboard interrupt received.")
    mock_app_instance.stop.assert_called_once()
    mock_logger_error.assert_not_called()


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
@patch("switchbot_actions.app.logger.info")
@patch("switchbot_actions.app.logger.error")
async def test_run_app_handles_unexpected_exception(
    mock_logger_error,
    mock_logger_info,
    mock_get_running_loop,
    mock_application_class,
):
    """Test that run_app handles unexpected exceptions gracefully."""
    mock_app_instance = mock_application_class.return_value
    mock_app_instance.start = AsyncMock(side_effect=ValueError("Something went wrong"))
    mock_app_instance.stop = AsyncMock()

    mock_loop = Mock()
    mock_get_running_loop.return_value = mock_loop

    await run_app(AppSettings(), argparse.Namespace())

    mock_loop.add_signal_handler.assert_called_once_with(
        signal.SIGHUP, mock_app_instance.reload_settings
    )
    mock_app_instance.start.assert_called_once()
    mock_logger_error.assert_any_call(
        "An unexpected error occurred: Something went wrong", exc_info=True
    )
    mock_app_instance.stop.assert_called_once()
    mock_logger_info.assert_not_called()


@pytest.mark.asyncio
@patch("switchbot_actions.app.logger.error")
@patch("switchbot_actions.exporter.start_http_server")
@patch("switchbot_actions.app.load_settings_from_cli")
async def test_reload_settings_with_invalid_config(
    mock_load_settings_from_cli,
    mock_start_http_server,
    mock_logger_error,
):
    """Test that reloading with invalid config does not crash and logs an error."""
    initial_settings = AppSettings(
        scanner=ScannerSettings(cycle=10, duration=3),
        prometheus_exporter=PrometheusExporterSettings(enabled=True, port=8000),
    )
    mock_load_settings_from_cli.return_value = initial_settings

    dummy_args = argparse.Namespace(config="/path/to/config.yaml")

    with patch("switchbot_actions.app.GetSwitchbotDevices"):
        app = Application(initial_settings, dummy_args)

    original_settings = app.settings

    # Assert http server port
    mock_start_http_server.assert_called_once_with(8000)
    mock_start_http_server.reset_mock()

    # Simulate failed reload with invalid YAML
    mock_load_settings_from_cli.side_effect = yaml.YAMLError("Error parsing YAML file")
    app.reload_settings()

    # Assert that settings have not changed and an error was logged for YAML parsing
    assert app.settings is original_settings
    mock_logger_error.assert_any_call(
        "Failed to reload configuration: Error parsing YAML file", exc_info=True
    )
    mock_logger_error.assert_any_call("Keeping the old configuration.")
    mock_logger_error.reset_mock()
