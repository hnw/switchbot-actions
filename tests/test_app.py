# tests/test_app.py

import argparse
import logging
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from switchbot_actions.app import Application, run_app
from switchbot_actions.component import ComponentError
from switchbot_actions.config import (
    AppSettings,
    AutomationRule,
)
from switchbot_actions.error import ConfigError

# Fixtures


@pytest.fixture
def cli_args():
    """Provides mock command-line arguments."""
    return argparse.Namespace(config="/path/to/config.yaml", verbose=0)


@pytest.fixture
def initial_settings():
    """Provides a default AppSettings instance for tests."""
    mock_rule = {
        "if": {"source": "switchbot", "device": "test_device"},
        "then": {"type": "log", "message": "test"},
        "name": "mock rule",
    }
    settings_dict = {
        "scanner": {"duration": 3, "wait": 1, "interface": 0},
        "mqtt": {"enabled": True, "host": "localhost", "port": 1883},
        "prometheus": {"enabled": True, "port": 8000},
        "automations": [mock_rule],
        "devices": {"test_device": {"address": "AA:BB:CC:DD:EE:FF"}},
    }
    return AppSettings.model_validate(settings_dict)


@pytest_asyncio.fixture
async def app_with_mocked_abstract_methods(initial_settings, cli_args):
    """
    Creates an Application instance and mocks its components' abstract methods.
    """
    app = Application(initial_settings, cli_args)

    for component in app._components.values():
        # Ensures all components start with _running = False for a clean test state.
        component._running = False

        # Mock abstract methods to control their behavior in tests.
        # This now works because the subclass signatures are fixed.
        component._is_enabled = MagicMock(side_effect=component._is_enabled)
        component._start = AsyncMock()
        component._stop = AsyncMock()
        component._require_restart = MagicMock(return_value=False)
        component._apply_live_update = AsyncMock()

    yield app


#  Initialization Tests


def test_application_always_creates_all_components(initial_settings, cli_args):
    """Test that Application always instantiates all components."""
    initial_settings.mqtt.enabled = False
    initial_settings.prometheus.enabled = False
    initial_settings.automations.rules = []

    app = Application(initial_settings, cli_args)

    assert "scanner" in app._components
    assert "mqtt" in app._components
    assert "prometheus" in app._components
    assert "automations" in app._components


# Start/Stop Tests


@pytest.mark.asyncio
async def test_start_calls_all_component_starts(app_with_mocked_abstract_methods):
    """Test that app.start() calls start() on all enabled component instances."""
    await app_with_mocked_abstract_methods.start()

    for component in app_with_mocked_abstract_methods._components.values():
        # Simulate the real method\'s behavior by setting the _running flag
        # after _start is called.
        if component.is_enabled:
            component._start.assert_awaited_once()
        else:
            component._start.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_stops_all_components_in_reverse_order(
    app_with_mocked_abstract_methods,
):
    """Test that app.stop() stops all components in reverse order of creation."""
    # Start the application to ensure components are in a running state for the test.
    await app_with_mocked_abstract_methods.start()
    # Manually set running state as mocks don't do it automatically
    for comp in app_with_mocked_abstract_methods._components.values():
        if comp.is_enabled:
            comp._running = True

    manager = MagicMock()
    manager.attach_mock(
        app_with_mocked_abstract_methods._components["scanner"]._stop, "scanner_stop"
    )
    manager.attach_mock(
        app_with_mocked_abstract_methods._components["mqtt"]._stop, "mqtt_stop"
    )
    manager.attach_mock(
        app_with_mocked_abstract_methods._components["prometheus"]._stop,
        "exporter_stop",
    )
    manager.attach_mock(
        app_with_mocked_abstract_methods._components["automations"]._stop,
        "handler_stop",
    )

    await app_with_mocked_abstract_methods.stop()

    for component in app_with_mocked_abstract_methods._components.values():
        if component.is_enabled:
            component._stop.assert_awaited_once()
        else:
            component._stop.assert_not_awaited()

    expected_call_order = [
        "handler_stop",
        "exporter_stop",
        "mqtt_stop",
        "scanner_stop",
    ]
    actual_call_order = [call[0] for call in manager.mock_calls]
    assert actual_call_order == expected_call_order


@pytest.mark.asyncio
async def test_start_components_error_propagation(app_with_mocked_abstract_methods):
    """Test that if a component fails to start, the exception propagates."""
    app_with_mocked_abstract_methods._components[
        "mqtt"
    ]._start.side_effect = ValueError("MQTT Boom")

    with pytest.raises(ComponentError, match="Failed to start MqttClient"):
        await app_with_mocked_abstract_methods.start()


# Reload Tests


@pytest.mark.asyncio
async def test_reload_settings_success_mqtt_restart(app_with_mocked_abstract_methods):
    """
    Test that when MQTT settings change (requiring restart), only MQTT component
    is stopped and started.
    """
    await app_with_mocked_abstract_methods.start()

    mock_mqtt = app_with_mocked_abstract_methods._components["mqtt"]
    mock_scanner = app_with_mocked_abstract_methods._components["scanner"]

    # Reset mock call counts to ensure accurate assertion of calls
    # made during the test action.
    mock_mqtt._start.reset_mock()
    mock_mqtt._stop.reset_mock()
    mock_scanner._apply_live_update.reset_mock()

    new_settings = deepcopy(app_with_mocked_abstract_methods.settings)
    new_settings.mqtt.host = "new_mqtt_host"

    mock_mqtt._require_restart.return_value = True

    with patch(
        "switchbot_actions.app.load_settings_from_cli", return_value=new_settings
    ):
        await app_with_mocked_abstract_methods.reload_settings()

        mock_mqtt._stop.assert_awaited_once()
        mock_mqtt._start.assert_awaited_once()
        mock_scanner._apply_live_update.assert_not_called()


@pytest.mark.asyncio
async def test_reload_settings_config_error(app_with_mocked_abstract_methods, caplog):
    """Test that a ConfigError on reload prevents changes and logs an error."""
    with patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings:
        mock_load_settings.side_effect = ConfigError("Invalid new config")

        await app_with_mocked_abstract_methods.reload_settings()

        assert "Failed to apply new configuration" in caplog.text
        assert "Invalid new config" in caplog.text


@pytest.mark.asyncio
async def test_reload_settings_rollback_fails(app_with_mocked_abstract_methods, caplog):
    """Test that a failure during rollback is a critical error and exits."""
    await app_with_mocked_abstract_methods.start()
    caplog.set_level(logging.INFO)

    with (
        patch("switchbot_actions.app.load_settings_from_cli") as mock_load_settings,
        patch("switchbot_actions.app.sys.exit") as mock_exit,
    ):
        new_settings = deepcopy(app_with_mocked_abstract_methods.settings)
        new_settings.scanner.wait = 99
        new_settings.mqtt.reconnect_interval = 99

        mock_load_settings.return_value = new_settings

        # Use a list for side_effect to simulate success on apply, failure on
        # rollback for the 'scanner' component.
        app_with_mocked_abstract_methods._components[
            "scanner"
        ]._apply_live_update.side_effect = [None, Exception("Scanner rollback failed")]

        # Make the 'mqtt' component's initial apply fail, which triggers the
        # rollback process.
        app_with_mocked_abstract_methods._components[
            "mqtt"
        ]._apply_live_update.side_effect = Exception("MQTT apply failed")

        await app_with_mocked_abstract_methods.reload_settings()

        assert "Failed to apply new configuration" in caplog.text
        assert "MQTT apply failed" in caplog.text  # Check for the initial failure
        assert "Rolling back to the previous configuration" in caplog.text

        # Assert the correct log message for the component that actually fails
        # during the rollback.
        assert "Failed to rollback settings for scanner" in caplog.text
        assert "Scanner rollback failed" in caplog.text
        mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_reload_settings_automation_handler_live_update_rules_change(
    app_with_mocked_abstract_methods,
):
    """
    Test that when AutomationHandler rules change, a live update is performed.
    """
    await app_with_mocked_abstract_methods.start()
    mock_automations = app_with_mocked_abstract_methods._components["automations"]

    new_settings = deepcopy(app_with_mocked_abstract_methods.settings)
    new_rule = {
        "if": {"source": "mqtt", "topic": "test/topic"},
        "then": [{"type": "log", "message": "new rule"}],
        "name": "new mock rule",
    }
    new_settings.automations.rules.append(AutomationRule.model_validate(new_rule))

    with patch(
        "switchbot_actions.app.load_settings_from_cli", return_value=new_settings
    ):
        await app_with_mocked_abstract_methods.reload_settings()

        mock_automations._apply_live_update.assert_awaited_once_with(
            new_settings.automations
        )


# run_app tests


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

        assert "Application encountered a critical error" in caplog.text
        assert "Address already in use" in caplog.text
        mock_exit.assert_called_once_with(1)
        mock_app.return_value.stop.assert_not_called()
