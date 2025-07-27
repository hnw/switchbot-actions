# tests/test_exporter.py

import pytest

from switchbot_actions.exporter import PrometheusExporter
from switchbot_actions.store import StateStore


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


def test_exporter_collect_metrics(mock_state_1):
    """Test that the exporter correctly generates metrics from the store."""
    storage = StateStore()
    storage._states[mock_state_1.address] = mock_state_1

    exporter = PrometheusExporter(state_storage=storage, port=8001, target_config={})
    metrics = list(exporter.collect())

    assert len(metrics) == 4  # temperature, humidity, battery, rssi
    temp_metric = next(m for m in metrics if m.name == "switchbot_temperature")
    assert len(temp_metric.samples) == 1
    assert temp_metric.samples[0].value == 22.5
    assert temp_metric.samples[0].labels["address"] == "DE:AD:BE:EF:33:33"

    rssi_metric = next(m for m in metrics if m.name == "switchbot_rssi")
    assert len(rssi_metric.samples) == 1
    assert rssi_metric.samples[0].value == -55
    assert rssi_metric.samples[0].labels["address"] == "DE:AD:BE:EF:33:33"


def test_metric_filtering(mock_state_1):
    """Test that metrics are filtered based on the target config."""
    storage = StateStore()
    storage._states[mock_state_1.address] = mock_state_1
    exporter = PrometheusExporter(
        state_storage=storage,
        port=8002,
        target_config={"metrics": ["temperature", "battery"]},
    )
    metrics = list(exporter.collect())
    assert len(metrics) == 2
    metric_names = {m.name for m in metrics}
    assert metric_names == {"switchbot_temperature", "switchbot_battery"}


def test_rssi_metric_filtering(mock_state_1):
    """Test that the rssi metric can be filtered."""
    storage = StateStore()
    storage._states[mock_state_1.address] = mock_state_1
    exporter = PrometheusExporter(
        state_storage=storage, port=8002, target_config={"metrics": ["rssi"]}
    )
    metrics = list(exporter.collect())
    assert len(metrics) == 1
    assert metrics[0].name == "switchbot_rssi"


def test_address_filtering(mock_state_1, mock_state_2):
    """Test that devices are filtered based on the target addresses."""
    storage = StateStore()
    storage._states[mock_state_1.address] = mock_state_1
    storage._states[mock_state_2.address] = mock_state_2

    exporter = PrometheusExporter(
        state_storage=storage,
        port=8003,
        target_config={"addresses": ["DE:AD:BE:EF:44:44"]},
    )
    metrics = list(exporter.collect())
    # Should only be metrics from the Bot device
    assert len(metrics) == 3  # battery, isOn, rssi
    battery_metric = next(m for m in metrics if m.name == "switchbot_battery")
    assert len(battery_metric.samples) == 1
    assert battery_metric.samples[0].labels["address"] == "DE:AD:BE:EF:44:44"
