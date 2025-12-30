# tests/test_exporter.py
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from prometheus_client import REGISTRY, CollectorRegistry

from switchbot_actions.config import DeviceSettings, PrometheusExporterSettings
from switchbot_actions.prometheus import PrometheusExporter
from switchbot_actions.signals import (
    action_executed,
    scan_executed,
    switchbot_advertisement_received,
)


@pytest.fixture
def test_registry():
    return CollectorRegistry()


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Removes test metrics from the REGISTRY after each test to ensure isolation."""
    yield
    metric_names_to_remove = [
        "switchbot_temperature",
        "switchbot_humidity",
        "switchbot_battery",
        "switchbot_rssi",
        "switchbot_isOn",
        "switchbot_device_info",
        "switchbot_scan_duration_seconds",
        "switchbot_advertisements",
    ]
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        if hasattr(collector, "_name") and collector._name in metric_names_to_remove:  # pyright:ignore[reportAttributeAccessIssue]
            REGISTRY.unregister(collector)


@pytest.fixture
def mock_state_1(mock_switchbot_advertisement):
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:33:33",
        rssi=-55,
        data={
            "modelName": "WoSensorTH",
            "data": {
                "temperature": 22.5,
                "humidity": 45,
                "battery": 88,
                "some_non_numeric": "value",
            },
        },
    )


@pytest.fixture
def mock_state_2(mock_switchbot_advertisement):
    return mock_switchbot_advertisement(
        address="DE:AD:BE:EF:44:44",
        rssi=-65,
        data={"modelName": "WoHand", "data": {"battery": 95, "isOn": True}},
    )


@pytest.fixture
def mock_state_unconfigured(mock_switchbot_advertisement):
    return mock_switchbot_advertisement(
        address="AA:BB:CC:DD:EE:FF",
        rssi=-70,
        data={"modelName": "Bot", "data": {"battery": 100}},
    )


@pytest.fixture
def configured_exporter_settings():
    return PrometheusExporterSettings(
        enabled=True,
        devices={
            "living_room_meter": {"address": "DE:AD:BE:EF:33:33"},
            "bedroom_bot": {"address": "DE:AD:BE:EF:44:44"},
        },
    )  # pyright:ignore[reportCallIssue]


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_info_metric_initialization(
    mock_start_http_server, configured_exporter_settings, test_registry
):
    """Test that switchbot_device_info is initialized correctly at startup."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    exporter = PrometheusExporter(
        settings=configured_exporter_settings, registry=test_registry
    )
    await exporter.start()

    # Verify initial state for living_room_meter
    info_value_lr = test_registry.get_sample_value(
        "switchbot_device_info",
        labels={
            "address": "DE:AD:BE:EF:33:33",
            "name": "living_room_meter",
            "model": "Unknown",
        },
    )
    assert info_value_lr == 1.0

    # Verify initial state for bedroom_bot
    info_value_bb = test_registry.get_sample_value(
        "switchbot_device_info",
        labels={
            "address": "DE:AD:BE:EF:44:44",
            "name": "bedroom_bot",
            "model": "Unknown",
        },
    )
    assert info_value_bb == 1.0

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_exporter_handle_advertisement(
    mock_start_http_server, mock_state_1, test_registry
):
    """Test that the exporter correctly handles an advertisement and updates gauges."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(enabled=True)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)

    await exporter.start()  # Await the start method

    # Send a signal to trigger `handle_advertisement`
    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    # Verify the value directly from the REGISTRY
    temp_value = test_registry.get_sample_value(
        "switchbot_temperature",
        labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
    )
    assert temp_value == 22.5

    rssi_value = test_registry.get_sample_value(
        "switchbot_rssi",
        labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
    )
    assert rssi_value == -55

    # Verify that non-numeric data does not create a gauge
    assert test_registry.get_sample_value("switchbot_some_non_numeric") is None

    await exporter.stop()  # Await the stop method


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_info_metric_update_on_advertisement(
    mock_start_http_server,
    configured_exporter_settings,
    mock_state_1,
    mock_state_unconfigured,
    test_registry,
):
    """Test that info metric is updated and unconfigured devices are ignored."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    exporter = PrometheusExporter(
        settings=configured_exporter_settings, registry=test_registry
    )
    await exporter.start()

    # Send advertisement for a configured device (mock_state_1)
    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    # Verify that the model name is updated for mock_state_1
    info_value_updated = test_registry.get_sample_value(
        "switchbot_device_info",
        labels={
            "address": "DE:AD:BE:EF:33:33",
            "name": "living_room_meter",
            "model": "WoSensorTH",
        },
    )
    assert info_value_updated == 1.0

    # Send advertisement for an unconfigured device (mock_state_unconfigured)
    switchbot_advertisement_received.send(exporter, new_state=mock_state_unconfigured)

    # Verify that no info metric is created for the unconfigured device
    info_value_unconfigured = test_registry.get_sample_value(
        "switchbot_device_info",
        labels={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "",  # Name will be empty as it's not in the map
            "model": "Bot",
        },
    )
    assert info_value_unconfigured is None

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_metric_filtering(mock_start_http_server, mock_state_1, test_registry):
    """Test that metrics are filtered based on the target config."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(
        enabled=True, target={"metrics": ["temperature", "battery"]}
    )  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)

    await exporter.start()  # Await the start method

    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    # Metric that should exist
    assert (
        test_registry.get_sample_value(
            "switchbot_temperature",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        == 22.5
    )
    # Filtered metric should be None
    assert (
        test_registry.get_sample_value(
            "switchbot_humidity",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        is None
    )

    await exporter.stop()  # Await the stop method


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_address_filtering(
    mock_start_http_server, mock_state_1, mock_state_2, test_registry
):
    """Test that devices are filtered based on the target addresses."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(
        enabled=True,
        target={"addresses": ["DE:AD:BE:EF:44:44"]},  # only mock_state_2
    )  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)

    await exporter.start()  # Await the start method

    mock_start_http_server.assert_called_once_with(
        settings.port, registry=test_registry
    )

    # Send signals for both devices
    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)
    switchbot_advertisement_received.send(exporter, new_state=mock_state_2)

    # Metric for mock_state_1 should be None
    assert (
        test_registry.get_sample_value(
            "switchbot_temperature",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        is None
    )
    # Metric for mock_state_2 should exist
    assert (
        test_registry.get_sample_value(
            "switchbot_isOn",
            labels={"address": "DE:AD:BE:EF:44:44", "model": "WoHand"},
        )
        == 1.0
    )

    await exporter.stop()  # Await the stop method


@pytest.mark.asyncio
async def test_start_does_not_call__start_if_disabled(test_registry):
    """
    Tests that the public start() method does not call the internal _start()
    if the component is disabled via its settings.
    """
    disabled_settings = PrometheusExporterSettings(enabled=False)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=disabled_settings, registry=test_registry)

    exporter._start = AsyncMock()

    await exporter.start()

    exporter._start.assert_not_called()


# --- Added Tests for Reload Logic ---


def test_require_restart_on_port_change(test_registry):
    """Tests that _require_restart returns True when the port changes."""
    settings = PrometheusExporterSettings(enabled=True, port=8000)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)

    new_settings = settings.model_copy()
    new_settings.port = 9000

    assert exporter._require_restart(new_settings) is True


def test_no_restart_on_other_settings_change(test_registry):
    """Tests that _require_restart returns False for non-critical changes."""
    settings = PrometheusExporterSettings(enabled=True)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)

    new_settings = settings.model_copy()
    new_settings.target = {"metrics": ["temperature"]}

    assert exporter._require_restart(new_settings) is False


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_apply_live_update_recreates_info_gauge(
    mock_start_http_server, test_registry
):
    """
    Tests that a live update correctly removes old device info metrics and
    creates new ones when the device list changes.
    """
    mock_start_http_server.return_value = [MagicMock(), Mock()]
    initial_settings = PrometheusExporterSettings(
        enabled=True,
        devices={
            "old_device": DeviceSettings(address="11:11:11:11:11:11"),
        },
    )  # pyright:ignore[reportCallIssue]

    exporter = PrometheusExporter(settings=initial_settings, registry=test_registry)
    await exporter.start()

    # Verify initial metric exists
    assert (
        test_registry.get_sample_value(
            "switchbot_device_info",
            labels={
                "address": "11:11:11:11:11:11",
                "name": "old_device",
                "model": "Unknown",
            },
        )
        == 1.0
    )

    # Prepare new settings and apply live update
    new_settings = PrometheusExporterSettings(
        enabled=True,
        devices={
            "new_device": DeviceSettings(address="22:22:22:22:22:22"),
        },
    )  # pyright:ignore[reportCallIssue]

    await exporter._apply_live_update(new_settings)
    exporter.settings = new_settings  # Simulate settings update by parent class

    # Verify old metric is gone
    assert (
        test_registry.get_sample_value(
            "switchbot_device_info",
            labels={
                "address": "11:11:11:11:11:11",
                "name": "old_device",
                "model": "Unknown",
            },
        )
        is None
    )

    # Verify new metric exists
    assert (
        test_registry.get_sample_value(
            "switchbot_device_info",
            labels={
                "address": "22:22:22:22:22:22",
                "name": "new_device",
                "model": "Unknown",
            },
        )
        == 1.0
    )

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_action_duration_histogram_updates(mock_start_http_server, test_registry):
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(enabled=True)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)
    await exporter.start()

    action_executed.send(exporter, action_type="webhook", duration=0.25)

    assert (
        test_registry.get_sample_value(
            "switchbot_action_duration_seconds_count",
            labels={"action_type": "webhook"},
        )
        == 1.0
    )
    assert test_registry.get_sample_value(
        "switchbot_action_duration_seconds_sum",
        labels={"action_type": "webhook"},
    ) == pytest.approx(0.25)

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_scan_duration_summary_updates(mock_start_http_server, test_registry):
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(enabled=True)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)
    await exporter.start()

    scan_executed.send(exporter, interface=0, scan_duration=1.25, cycle_duration=1.75)

    assert (
        test_registry.get_sample_value(
            "switchbot_scan_duration_seconds_count",
            labels={"interface": "0"},
        )
        == 1.0
    )
    assert test_registry.get_sample_value(
        "switchbot_scan_duration_seconds_sum",
        labels={"interface": "0"},
    ) == pytest.approx(1.25)

    assert test_registry.get_sample_value(
        "switchbot_cycle_duration_seconds_sum",
        labels={"interface": "0"},
    ) == pytest.approx(1.75)

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_advertisements_counter_increments(
    mock_start_http_server, mock_state_1, test_registry
):
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(enabled=True)  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)
    await exporter.start()

    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    assert (
        test_registry.get_sample_value(
            "switchbot_advertisements_total",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        == 1.0
    )

    await exporter.stop()


@pytest.mark.asyncio
@patch("switchbot_actions.prometheus.start_http_server")
async def test_advertisements_counter_respects_address_filtering(
    mock_start_http_server, mock_state_1, mock_state_2, test_registry
):
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(
        enabled=True,
        target={"addresses": ["DE:AD:BE:EF:44:44"]},  # only mock_state_2
    )  # pyright:ignore[reportCallIssue]
    exporter = PrometheusExporter(settings=settings, registry=test_registry)
    await exporter.start()

    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)
    switchbot_advertisement_received.send(exporter, new_state=mock_state_2)

    assert (
        test_registry.get_sample_value(
            "switchbot_advertisements_total",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        is None
    )
    assert (
        test_registry.get_sample_value(
            "switchbot_advertisements_total",
            labels={"address": "DE:AD:BE:EF:44:44", "model": "WoHand"},
        )
        == 1.0
    )

    await exporter.stop()
