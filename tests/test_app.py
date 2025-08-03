import argparse
import asyncio
import signal
from copy import deepcopy
from http.server import HTTPServer
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from switchbot_actions.app import Application, run_app
from switchbot_actions.config import (
    AppSettings,
    MqttSettings,
    PrometheusExporterSettings,
)
from switchbot_actions.error import ConfigError

# Fixtures


@pytest.fixture
def mock_ble_scanner():
    with patch("switchbot_actions.app.GetSwitchbotDevices") as mock:
        yield mock


@pytest.fixture
def cli_args():
    return argparse.Namespace(config="/path/to/config.yaml")


@pytest.fixture
def initial_settings():
    return AppSettings(
        mqtt=MqttSettings(host="localhost", port=1883),
        prometheus_exporter=PrometheusExporterSettings(enabled=True, port=8000),
    )


@pytest.fixture
@patch("switchbot_actions.app.SwitchbotClient")
@patch("switchbot_actions.app.PrometheusExporter")
@patch("switchbot_actions.app.MqttClient")
def app(
    mock_mqtt, mock_exporter, mock_scanner, initial_settings, cli_args, mock_ble_scanner
):
    # Prevent component start methods from running during initialization
    with patch.object(Application, "_start_components") as _:
        application = Application(initial_settings, cli_args)
        # Manually set mocks after init
        application.mqtt_client = mock_mqtt.return_value
        application.exporter = mock_exporter.return_value
        application.scanner = mock_scanner.return_value
        return application


# Tests


def test_initialization(app, initial_settings):
    """Test that all components are initialized on Application start."""
    with (
        patch.object(app, "_start_mqtt") as m_mqtt,
        patch.object(app, "_start_exporter") as m_exporter,
        patch.object(app, "_start_automations") as m_auto,
    ):
        app._start_components()
        m_mqtt.assert_called_once()
        m_exporter.assert_called_once()
        m_auto.assert_called_once()


@pytest.mark.asyncio
async def test_stop(app):
    """Test that all components are stopped on Application stop."""
    with (
        patch.object(app, "_stop_mqtt", new_callable=AsyncMock) as m_mqtt,
        patch.object(app, "_stop_exporter") as m_exporter,
        patch.object(app, "_stop_automations") as m_auto,
    ):
        await app._stop_components()
        m_mqtt.assert_called_once()
        m_exporter.assert_called_once()
        m_auto.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
@patch("switchbot_actions.app.logger")
async def test_reload_no_changes(
    mock_logger, mock_load_settings, app, initial_settings
):
    """Test that no components are restarted if the configuration hasn't changed."""
    mock_load_settings.return_value = deepcopy(initial_settings)
    with patch.object(app, "_stop_changed_components") as mock_stop:
        await app.reload_settings()
        mock_logger.info.assert_any_call("No configuration changes detected.")
        mock_stop.assert_not_called()


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
@patch("switchbot_actions.app.logger")
async def test_reload_single_component_change(
    mock_logger, mock_load_settings, app, initial_settings
):
    """Test that only the changed component is restarted."""
    new_settings = deepcopy(initial_settings)
    new_settings.mqtt.host = "new-broker"

    mock_load_settings.return_value = new_settings

    with (
        patch.object(
            app, "_stop_changed_components", new_callable=AsyncMock
        ) as mock_stop,
        patch.object(app, "_start_changed_components") as mock_start,
    ):
        await app.reload_settings()

        mock_logger.info.assert_any_call("Configuration changed for: mqtt")
        mock_stop.assert_called_once_with(["mqtt"])
        mock_start.assert_called_once_with(["mqtt"])


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
@patch("switchbot_actions.app.logger")
async def test_reload_failure_and_rollback(
    mock_logger, mock_load_settings, app, initial_settings
):
    """Test that a failed reload triggers a rollback to the old settings."""
    new_settings = deepcopy(initial_settings)
    new_settings.mqtt.host = "invalid-broker-that-will-fail"

    mock_load_settings.return_value = new_settings

    original_settings = app.settings

    with (
        patch.object(app, "_stop_changed_components", new_callable=AsyncMock),
        patch.object(app, "_start_mqtt") as mock_start_mqtt,
        patch.object(app, "_start_exporter") as mock_start_exporter,
        patch.object(app, "_start_automations") as mock_start_automations,
    ):
        # Simulate initial start failure
        mock_start_mqtt.side_effect = [Exception("Initial Start Failed"), None]

        await app.reload_settings()

        assert app.settings is original_settings
        mock_logger.error.assert_any_call(
            "Failed to apply new configuration: Initial Start Failed",
            exc_info=True,
        )
        mock_logger.info.assert_any_call("Rolling back to the previous configuration.")
        mock_logger.info.assert_any_call("Rollback successful.")

        # Assert that _start_mqtt was called twice
        # (once for initial attempt, once for rollback)
        assert mock_start_mqtt.call_count == 2

        # Assert that other start methods were NOT called
        mock_start_exporter.assert_not_called()
        mock_start_automations.assert_not_called()


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
@patch("switchbot_actions.app.logger")
async def test_reload_config_load_error(mock_logger, mock_load_settings, app):
    """Test that the application handles errors during config file loading."""
    mock_load_settings.side_effect = ConfigError("Invalid YAML")
    original_settings = app.settings

    await app.reload_settings()

    assert app.settings is original_settings
    mock_logger.error.assert_any_call(
        "Failed to load new configuration, keeping the old. Reason:\nInvalid YAML"
    )


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
async def test_run_app_signal_handler(mock_get_loop, mock_app_class):
    """Test that the SIGHUP signal handler is registered."""
    mock_loop = Mock()
    mock_get_loop.return_value = mock_loop
    mock_app_instance = mock_app_class.return_value
    mock_app_instance.start = AsyncMock()
    mock_app_instance.stop = AsyncMock()
    mock_app_instance.reload_settings = AsyncMock()

    await run_app(AppSettings(), argparse.Namespace())

    # Get the lambda function passed to add_signal_handler
    args, kwargs = mock_loop.add_signal_handler.call_args
    signal_num, handler_func = args
    assert signal_num == signal.SIGHUP

    # Call the lambda to ensure it calls the correct method
    handler_func()

    mock_app_instance.reload_settings.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
async def test_run_app_keyboard_interrupt(mock_get_loop, mock_app_class, caplog):
    """Test that KeyboardInterrupt is handled gracefully."""
    mock_loop = Mock()
    mock_get_loop.return_value = mock_loop
    mock_app_instance = mock_app_class.return_value
    mock_app_instance.start = AsyncMock(side_effect=KeyboardInterrupt)
    mock_app_instance.stop = AsyncMock()

    with patch("switchbot_actions.app.logger") as mock_logger:
        await run_app(AppSettings(), argparse.Namespace())
        mock_logger.info.assert_any_call("Keyboard interrupt received.")
        mock_app_instance.stop.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
async def test_run_app_unexpected_error(mock_get_loop, mock_app_class, caplog):
    """Test that unexpected errors are caught and logged."""
    mock_loop = Mock()
    mock_get_loop.return_value = mock_loop
    mock_app_instance = mock_app_class.return_value
    test_exception = Exception("Unexpected Error")
    mock_app_instance.start = AsyncMock(side_effect=test_exception)
    mock_app_instance.stop = AsyncMock()

    with patch("switchbot_actions.app.logger") as mock_logger:
        await run_app(AppSettings(), argparse.Namespace())
        mock_logger.error.assert_any_call(
            "An unexpected error occurred: Unexpected Error", exc_info=True
        )
        mock_app_instance.stop.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
async def test_reload_integration_with_real_components(
    mock_load_settings, cli_args, mock_ble_scanner, caplog
):
    """
    Integration test for the reload functionality with real component instances.
    Verifies that MQTT and Prometheus components are correctly stopped and restarted.
    """
    # Initial settings
    initial_settings = AppSettings(
        mqtt=MqttSettings(host="localhost", port=1883),
        prometheus_exporter=PrometheusExporterSettings(enabled=True, port=8001),
    )

    # New settings for reload
    new_settings = deepcopy(initial_settings)
    assert new_settings.mqtt is not None
    new_settings.mqtt.port = 1884
    assert new_settings.prometheus_exporter is not None
    new_settings.prometheus_exporter.port = 8002

    mock_load_settings.return_value = new_settings

    # Mock the parts that interact with external systems
    with (
        patch("switchbot_actions.mqtt.aiomqtt.Client") as mock_aiomqtt_client_class,
        patch("switchbot_actions.exporter.start_http_server") as mock_start_http_server,
    ):
        # --- Mock aiomqtt.Client ---
        mock_mqtt_client = AsyncMock()  # The instance

        # Make the instance an async context manager
        mock_mqtt_client.__aenter__.return_value = mock_mqtt_client
        mock_mqtt_client.__aexit__.return_value = None

        # Make `messages` an async iterable that will stay pending until cancelled
        async def mock_messages_iterator():
            await asyncio.sleep(3600)  # A long time
            yield  # This will never be reached

        mock_mqtt_client.messages = mock_messages_iterator()

        # The class returns our mocked instance
        mock_aiomqtt_client_class.return_value = mock_mqtt_client

        # --- Mock Prometheus server ---
        mock_http_server = MagicMock(spec=HTTPServer)
        mock_start_http_server.return_value = (mock_http_server, Mock())

        # --- Run Test ---
        app = Application(initial_settings, cli_args)
        assert app.mqtt_task is not None
        initial_mqtt_task = app.mqtt_task

        # Simulate SIGHUP to trigger reload
        await app.reload_settings()

        # Allow the event loop to process the cancellation and new task creation
        await asyncio.sleep(0)

        # Assertions
        # 1. MQTT client was restarted
        assert app.mqtt_task is not None
        assert app.mqtt_task != initial_mqtt_task
        assert initial_mqtt_task.cancelled()

        # 2. Prometheus exporter was restarted
        mock_http_server.shutdown.assert_called_once()
        mock_start_http_server.assert_called_with(new_settings.prometheus_exporter.port)

        # 3. Settings were updated
        assert app.settings.mqtt is not None
        assert app.settings.mqtt.port == 1884
        assert app.settings.prometheus_exporter is not None
        assert app.settings.prometheus_exporter.port == 8002

        # Clean up the application to avoid resource warnings
        await app.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.app.load_settings_from_cli")
@patch("switchbot_actions.app.logger")
async def test_reload_and_rollback_failure_exits(
    mock_logger, mock_load_settings, app, initial_settings
):
    """
    Test that if rollback fails, the application exits with status code 1.
    """
    new_settings = deepcopy(initial_settings)
    new_settings.mqtt.host = "new-broker"

    mock_load_settings.return_value = new_settings

    with (
        patch.object(app, "_stop_changed_components", new_callable=AsyncMock),
        patch.object(
            app,
            "_start_changed_components",
            side_effect=[
                Exception("Initial Start Failed"),
                Exception("Rollback Failed"),
            ],
        ),
        pytest.raises(SystemExit) as excinfo,
    ):
        await app.reload_settings()

        mock_logger.critical.assert_any_call(
            "Rollback failed: Rollback Failed", exc_info=True
        )
        assert excinfo.value.code == 1


@pytest.mark.asyncio
@patch("switchbot_actions.exporter.logger")
@patch("switchbot_actions.app.PrometheusExporter")
@patch("switchbot_actions.app.logger")
async def test_prometheus_exporter_port_in_use_error(
    mock_app_logger,
    mock_prometheus_exporter_class,
    mock_exporter_logger,
    initial_settings,
    cli_args,
):
    """
    Test that the application handles OSError when Prometheus exporter port is in use.
    """
    # Configure the mock PrometheusExporter to raise OSError during start_server
    mock_exporter_instance = Mock()
    mock_prometheus_exporter_class.return_value = mock_exporter_instance
    mock_exporter_instance.start.side_effect = OSError("Address already in use")

    # Call run_app, which should catch the OSError and exit
    with pytest.raises(SystemExit) as excinfo:
        await run_app(initial_settings, cli_args)

    assert excinfo.value.code == 1

    mock_app_logger.critical.assert_any_call(
        "Application encountered a critical error during startup and will exit: "
        "Address already in use",
        exc_info=True,
    )


@patch("switchbot_actions.app.Application._start_components")
@patch("switchbot_actions.app.setup_logging")
def test_application_init_calls_setup_logging(
    mock_setup_logging,
    mock_start_components,
    initial_settings,
    cli_args,
):
    """Test that Application.__init__ calls setup_logging with the correct settings."""
    _ = Application(initial_settings, cli_args)

    mock_setup_logging.assert_called_once_with(initial_settings)
    mock_start_components.assert_called_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.setup_logging")
@patch("switchbot_actions.app.load_settings_from_cli")
async def test_reload_settings_calls_setup_logging(
    mock_load_settings,
    mock_setup_logging,
    app,
):
    """Test that reload_settings calls setup_logging with the new settings."""
    new_settings = deepcopy(app.settings)
    new_settings.debug = True
    mock_load_settings.return_value = new_settings

    mock_setup_logging.reset_mock()

    await app.reload_settings()

    mock_setup_logging.assert_called_once_with(new_settings)
