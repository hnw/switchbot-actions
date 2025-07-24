# tests/test_evaluator.py
from unittest.mock import MagicMock

import pytest
from switchbot import SwitchBotAdvertisement

from switchbot_actions import evaluator


@pytest.fixture
def sample_state() -> SwitchBotAdvertisement:
    """A sample SwitchBotAdvertisement object for testing."""
    return SwitchBotAdvertisement(
        address="e1:22:33:44:55:66",
        data={
            "data": {"temperature": 25.0, "humidity": 50, "battery": 100},
            "modelName": "WoSensorTH",
        },
        rssi=-50,
        device=MagicMock(),
    )


def test_get_state_key(sample_state):
    """Test that get_state_key returns the MAC address."""
    assert evaluator.get_state_key(sample_state) == "e1:22:33:44:55:66"


@pytest.mark.parametrize(
    "condition, value, expected",
    [
        ("== 25.0", 25.0, True),
        ("25", 25.0, True),
        ("> 20", 25.0, True),
        ("< 30", 25.0, True),
        ("!= 30", 25.0, True),
        ("true", True, True),
        ("false", False, True),
        ("invalid", 123, False),
    ],
)
def test_evaluate_condition(condition, value, expected):
    """Test various condition evaluations."""
    assert evaluator.evaluate_condition(condition, value) == expected


def test_check_conditions_device_pass(sample_state):
    """Test that device conditions pass."""
    if_config = {"device": {"address": "e1:22:33:44:55:66", "modelName": "WoSensorTH"}}
    assert evaluator.check_conditions(if_config, sample_state) is True


def test_check_conditions_device_fail(sample_state):
    """Test that device conditions fail."""
    if_config = {"device": {"address": "e1:22:33:44:55:66", "modelName": "WoPresence"}}
    assert evaluator.check_conditions(if_config, sample_state) is False


def test_check_conditions_state_pass(sample_state):
    """Test that state conditions pass."""
    if_config = {"state": {"temperature": "> 20", "humidity": "< 60"}}
    assert evaluator.check_conditions(if_config, sample_state) is True


def test_check_conditions_state_fail(sample_state):
    """Test that state conditions fail."""
    if_config = {"state": {"temperature": "> 30"}}
    assert evaluator.check_conditions(if_config, sample_state) is False


def test_check_conditions_rssi(sample_state):
    """Test that RSSI conditions are checked correctly."""
    if_config = {"state": {"rssi": "> -60"}}
    assert evaluator.check_conditions(if_config, sample_state) is True
    if_config = {"state": {"rssi": "< -60"}}
    assert evaluator.check_conditions(if_config, sample_state) is False
