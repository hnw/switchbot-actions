from unittest.mock import MagicMock

import aiomqtt
import pytest
from switchbot import SwitchBotAdvertisement


@pytest.fixture
def mock_switchbot_advertisement():
    """A factory for creating mock SwitchBotAdvertisement objects."""

    def _factory(**kwargs):
        default_data = {
            "address": "e1:22:33:44:55:66",
            "data": {
                "data": {"temperature": 25.0, "humidity": 50, "battery": 100},
                "modelName": "WoSensorTH",
            },
            "rssi": -50,
            "device": MagicMock(),
        }
        default_data.update(kwargs)
        return SwitchBotAdvertisement(**default_data)

    return _factory


@pytest.fixture
def mqtt_message_plain() -> aiomqtt.Message:
    """A sample aiomqtt.Message object with plain text payload."""
    message = aiomqtt.Message(
        topic=aiomqtt.Topic("test/topic"),
        payload=b"ON",
        qos=1,
        retain=False,
        mid=1,
        properties=None,
    )
    return message


@pytest.fixture
def mqtt_message_json() -> aiomqtt.Message:
    """A sample aiomqtt.Message object with JSON payload."""
    message = aiomqtt.Message(
        topic=aiomqtt.Topic("home/sensor1"),
        payload=b'{"temperature": 28.5, "humidity": 55}',
        qos=1,
        retain=False,
        mid=1,
        properties=None,
    )
    return message


@pytest.fixture
def sample_state(mock_switchbot_advertisement):
    """A sample StateObject (SwitchBotState) for testing purposes."""
    raw_state = mock_switchbot_advertisement(
        address="e1:22:33:44:55:66",
        data={
            "data": {"temperature": 25.0, "humidity": 50, "battery": 100},
            "modelName": "WoSensorTH",
        },
        rssi=-50,
    )
    from switchbot_actions.evaluator import create_state_object

    return create_state_object(raw_state)
