# tests/test_exporter.py
from unittest.mock import MagicMock, Mock, patch

import pytest
from prometheus_client import REGISTRY

from switchbot_actions.config import PrometheusExporterSettings
from switchbot_actions.exporter import PrometheusExporter
from switchbot_actions.signals import switchbot_advertisement_received


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
    ]
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        if hasattr(collector, "_name") and collector._name in metric_names_to_remove:  # type: ignore[attr-defined]
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


@patch("switchbot_actions.exporter.start_http_server")
def test_exporter_handle_advertisement(mock_start_http_server, mock_state_1):
    """Test that the exporter correctly handles an advertisement and updates gauges."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(enabled=True)  # type: ignore[call-arg]
    exporter = PrometheusExporter(settings=settings)

    exporter.start()

    # Send a signal to trigger `handle_advertisement`
    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    # Verify the value directly from the REGISTRY
    temp_value = REGISTRY.get_sample_value(
        "switchbot_temperature",
        labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
    )
    assert temp_value == 22.5

    rssi_value = REGISTRY.get_sample_value(
        "switchbot_rssi",
        labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
    )
    assert rssi_value == -55

    # Verify that non-numeric data does not create a gauge
    assert REGISTRY.get_sample_value("switchbot_some_non_numeric") is None


@patch("switchbot_actions.exporter.start_http_server")
def test_metric_filtering(mock_start_http_server, mock_state_1):
    """Test that metrics are filtered based on the target config."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(
        enabled=True, target={"metrics": ["temperature", "battery"]}
    )  # type: ignore[call-arg]
    exporter = PrometheusExporter(settings=settings)

    exporter.start()

    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)

    # Metric that should exist
    assert (
        REGISTRY.get_sample_value(
            "switchbot_temperature",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        == 22.5
    )
    # Filtered metric should be None
    assert (
        REGISTRY.get_sample_value(
            "switchbot_humidity",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        is None
    )


@patch("switchbot_actions.exporter.start_http_server")
def test_address_filtering(mock_start_http_server, mock_state_1, mock_state_2):
    """Test that devices are filtered based on the target addresses."""
    mock_start_http_server.return_value = [MagicMock(), Mock()]

    settings = PrometheusExporterSettings(
        enabled=True,
        target={"addresses": ["DE:AD:BE:EF:44:44"]},  # only mock_state_2
    )  # type: ignore[call-arg]
    exporter = PrometheusExporter(settings=settings)

    exporter.start()

    mock_start_http_server.assert_called_once_with(settings.port)

    # Send signals for both devices
    switchbot_advertisement_received.send(exporter, new_state=mock_state_1)
    switchbot_advertisement_received.send(exporter, new_state=mock_state_2)

    # Metric for mock_state_1 should be None
    assert (
        REGISTRY.get_sample_value(
            "switchbot_temperature",
            labels={"address": "DE:AD:BE:EF:33:33", "model": "WoSensorTH"},
        )
        is None
    )
    # Metric for mock_state_2 should exist
    assert (
        REGISTRY.get_sample_value(
            "switchbot_isOn",
            labels={"address": "DE:AD:BE:EF:44:44", "model": "WoHand"},
        )
        == 1.0
    )
