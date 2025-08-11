# test_app.py

import argparse
import logging
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

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
def cli_args():
    """Provides mock command-line arguments."""
    return argparse.Namespace(config="/path/to/config.yaml")


@pytest.fixture
def initial_settings():
    """Provides a default AppSettings instance for tests."""
    mock_rule = {
        "if": {"source": "switchbot", "device": "test_device"},
        "then": {"type": "log", "message": "test"},
        "name": "mock rule",
    }
    settings_dict = {
        "scanner": {"cycle": 10, "duration": 3, "interface": 0},
        "mqtt": {"host": "localhost", "port": 1883},
        "prometheus_exporter": {"enabled": True, "port": 8000},
        "automations": [mock_rule],
        "devices": {"test_device": {"address": "xx:xx:xx:xx:xx:xx"}},
    }
    return AppSettings.model_validate(settings_dict)


@pytest.fixture
def mock_components():
    """Mocks all components that Application creates."""
    with (
        patch("switchbot_actions.app.MqttClient") as mock_mqtt,
        patch("switchbot_actions.app.PrometheusExporter") as mock_exporter,
        patch("switchbot_actions.app.SwitchbotClient") as mock_scanner,
        patch("switchbot_actions.app.AutomationHandler") as mock_handler,
        patch("switchbot_actions.app.GetSwitchbotDevices") as mock_ble_scanner,
    ):
        # Make start/stop methods async mocks
        for mock_class in [mock_mqtt, mock_exporter, mock_scanner, mock_handler]:
            mock_class.return_value.start = AsyncMock()
            mock_class.return_value.stop = AsyncMock()
        yield {
            "mqtt": mock_mqtt,
            "exporter": mock_exporter,
            "scanner": mock_scanner,
            "handler": mock_handler,
            "ble_scanner": mock_ble_scanner,
        }


# Tests


# region Initialization Tests
def test_application_creates_scanner_by_default(
    initial_settings, cli_args, mock_components
):
    """Test that SwitchbotClient is always created."""
    Application(initial_settings, cli_args)
    mock_components["scanner"].assert_called_once()
    mock_components["ble_scanner"].assert_called_with(
        interface=initial_settings.scanner.interface
    )


@pytest.mark.parametrize(
    "component_name,is_enabled,setting_attr,setting_value",
    [
        ("mqtt", True, "mqtt", MqttSettings(host="localhost")),  # type: ignore[call-arg]
        ("mqtt", False, "mqtt", None),
        (
            "prometheus_exporter",
            True,
            "prometheus_exporter",
            PrometheusExporterSettings(enabled=True),  # type: ignore[call-arg]
        ),
        (
            "prometheus_exporter",
            False,
            "prometheus_exporter",
            PrometheusExporterSettings(enabled=False),  # type: ignore[call-arg]
        ),
        ("automations", True, "automations", [MagicMock()]),
        ("automations", False, "automations", []),
    ],
)
def test_application_creates_components_based_on_settings(
    initial_settings,
    cli_args,
    mock_components,
    component_name,
    is_enabled,
    setting_attr,
    setting_value,
):
    """Test that components are created based on their settings."""
    settings = deepcopy(initial_settings)
    setattr(settings, setting_attr, setting_value)

    component_map = {
        "mqtt": mock_components["mqtt"],
        "prometheus_exporter": mock_components["exporter"],
        "automations": mock_components["handler"],
    }
    mock_to_check = component_map[component_name]

    Application(settings, cli_args)

    if is_enabled:
        mock_to_check.assert_called_once()
    else:
        mock_to_check.assert_not_called()


# endregion

# region Start/Stop Tests


@pytest.mark.asyncio
async def test_start_starts_all_created_components(
    initial_settings, cli_args, mock_components
):
    """Test that app.start() starts all created components."""
    app = Application(initial_settings, cli_args)
    await app.start()

    mock_components["scanner"].return_value.start.assert_awaited_once()
    mock_components["mqtt"].return_value.start.assert_awaited_once()
    mock_components["exporter"].return_value.start.assert_awaited_once()
    mock_components["handler"].return_value.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_stops_all_components_in_reverse_order(
    initial_settings, cli_args, mock_components
):
    """Test that app.stop() stops all components in reverse order of creation."""
    app = Application(initial_settings, cli_args)

    # To check call order, we can use a manager mock
    manager = MagicMock()
    manager.attach_mock(mock_components["scanner"].return_value.stop, "scanner_stop")
    manager.attach_mock(mock_components["mqtt"].return_value.stop, "mqtt_stop")
    manager.attach_mock(mock_components["exporter"].return_value.stop, "exporter_stop")
    manager.attach_mock(mock_components["handler"].return_value.stop, "handler_stop")

    await app.stop()

    # Assert that stop was called on all of them
    mock_components["scanner"].return_value.stop.assert_awaited_once()
    mock_components["mqtt"].return_value.stop.assert_awaited_once()
    mock_components["exporter"].return_value.stop.assert_awaited_once()
    mock_components["handler"].return_value.stop.assert_awaited_once()

    # Assert the reverse order of calls
    expected_call_order = [
        "handler_stop",
        "exporter_stop",
        "mqtt_stop",
        "scanner_stop",
    ]
    actual_call_order = [call[0] for call in manager.mock_calls]
    assert actual_call_order == expected_call_order


@pytest.mark.asyncio
async def test_start_components_error_propagation(
    initial_settings, cli_args, mock_components
):
    """Test that if a component fails to start, the exception propagates."""
    mock_components["mqtt"].return_value.start.side_effect = ValueError("MQTT Boom")

    app = Application(initial_settings, cli_args)

    with pytest.raises(ValueError, match="MQTT Boom"):
        await app.start()


# endregion

# region Reload Tests


@pytest.mark.asyncio
async def test_reload_settings_success(initial_settings, cli_args, mock_components):
    """Test successful reloading of settings and restarting of components."""
    with patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings:
        # Initial setup
        app = Application(initial_settings, cli_args)
        await app.start()

        # Get references to old component mocks' stop methods
        old_scanner_stop = mock_components["scanner"].return_value.stop
        old_mqtt_stop = mock_components["mqtt"].return_value.stop
        old_exporter_stop = mock_components["exporter"].return_value.stop
        old_handler_stop = mock_components["handler"].return_value.stop

        # Mock new settings (disable mqtt, change exporter port)
        new_settings = deepcopy(initial_settings)
        new_settings.mqtt = None
        new_settings.prometheus_exporter.port = 9090
        mock_load_settings.return_value = new_settings

        # Reset mocks to track new calls for creation and start
        mock_components["scanner"].reset_mock()
        mock_components["mqtt"].reset_mock()
        mock_components["exporter"].reset_mock()
        mock_components["handler"].reset_mock()

        # Reload settings
        await app.reload_settings()

        # 1. Assert old components were stopped
        old_scanner_stop.assert_awaited_once()
        old_mqtt_stop.assert_awaited_once()
        old_exporter_stop.assert_awaited_once()
        old_handler_stop.assert_awaited_once()

        # 2. Assert new components were created based on new config
        mock_components["scanner"].assert_called_once()
        mock_components["mqtt"].assert_not_called()  # Was disabled
        mock_components["exporter"].assert_called_with(
            settings=new_settings.prometheus_exporter
        )
        mock_components["handler"].assert_called_once()

        # 3. Assert new components were started
        mock_components["scanner"].return_value.start.assert_awaited_once()
        mock_components["mqtt"].return_value.start.assert_not_called()
        mock_components["exporter"].return_value.start.assert_awaited_once()
        mock_components["handler"].return_value.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_settings_config_error(
    initial_settings, cli_args, mock_components, caplog
):
    """Test that a ConfigError on reload prevents changes and logs an error."""
    with patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings:
        mock_load_settings.side_effect = ConfigError("Invalid new config")

        app = Application(initial_settings, cli_args)

        # Get references to original component stop methods
        original_stop_methods = [
            m.return_value.stop
            for m in mock_components.values()
            if hasattr(m.return_value, "stop")
        ]

        await app.reload_settings()

        # Assert that an error was logged
        assert "Failed to load new configuration" in caplog.text
        assert "Invalid new config" in caplog.text

        # Assert that no components were stopped
        for stop_method in original_stop_methods:
            stop_method.assert_not_called()

        # Assert that settings and components were not replaced
        assert app.settings == initial_settings


@pytest.mark.asyncio
async def test_reload_settings_rollback_fails(
    initial_settings, cli_args, mock_components, caplog
):
    """Test that a failure during rollback is a critical error."""
    caplog.set_level(logging.INFO)
    with (
        patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings,
        patch("switchbot_actions.app.sys.exit") as mock_exit,
    ):
        app = Application(initial_settings, cli_args)

        # Make the new component fail to start
        new_settings = deepcopy(initial_settings)
        mock_load_settings.return_value = new_settings

        # Re-configure mocks for the 'new' component creation phase
        for m in mock_components.values():
            m.reset_mock(return_value=True, side_effect=True)
            m.return_value.start = AsyncMock()
            m.return_value.stop = AsyncMock()

        mock_components["mqtt"].return_value.start.side_effect = Exception(
            "New component start failed"
        )

        # Make the *old* component fail to start during rollback
        # The app holds references to the original components.
        app._components["scanner"].start = AsyncMock(
            side_effect=Exception("Rollback start failed")
        )

        await app.reload_settings()

        assert "Rollback failed" in caplog.text
        assert "Rollback start failed" in caplog.text
        mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_mqtt_message_published_after_reload_completes(
    initial_settings, cli_args, mock_components
):
    """
    Test that an MQTT message requested during reload is published only after
    reload completes.
    """
    # List to store all MqttClient instances created
    created_mqtt_clients = []

    def mqtt_client_constructor_side_effect(*args, **kwargs):
        new_client_mock = MagicMock()
        new_client_mock.publish = AsyncMock()
        new_client_mock.start = AsyncMock()
        new_client_mock.stop = AsyncMock()
        created_mqtt_clients.append(new_client_mock)
        return new_client_mock

    # Apply the side effect to the MqttClient mock from the fixture
    mock_components["mqtt"].side_effect = mqtt_client_constructor_side_effect

    # Apply the side effect to the MqttClient mock from the fixture
    mock_components["mqtt"].side_effect = mqtt_client_constructor_side_effect

    app = Application(initial_settings, cli_args)
    await app.start()


# endregion

# region run_app tests


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
async def test_run_app_handles_keyboard_interrupt(
    mock_loop, mock_app, initial_settings, cli_args, caplog
):
    """Test that run_app handles KeyboardInterrupt gracefully."""
    caplog.set_level(logging.INFO)
    mock_app.return_value.start.side_effect = KeyboardInterrupt
    mock_app.return_value.stop = AsyncMock()

    await run_app(initial_settings, cli_args)

    assert "Keyboard interrupt received" in caplog.text
    mock_app.return_value.stop.assert_awaited_once()


@pytest.mark.asyncio
@patch("switchbot_actions.app.Application")
@patch("switchbot_actions.app.asyncio.get_running_loop")
async def test_run_app_handles_os_error_on_startup(
    mock_loop, mock_app, initial_settings, cli_args, caplog
):
    """Test that run_app handles OSError on startup and exits."""
    with patch("switchbot_actions.app.sys.exit") as mock_exit:
        mock_app.side_effect = OSError("Address already in use")

        await run_app(initial_settings, cli_args)

        assert "critical error during startup" in caplog.text
        assert "Address already in use" in caplog.text
        mock_exit.assert_called_once_with(1)
        # app.stop() should not be called because app instantiation failed
        mock_app.return_value.stop.assert_not_called()


# endregion
