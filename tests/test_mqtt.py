from unittest.mock import AsyncMock, patch

import pytest
from aiomqtt import MqttError

from switchbot_actions.config import MqttSettings
from switchbot_actions.mqtt import MqttClient, mqtt_message_received


@pytest.fixture
def mock_aiomqtt_client():
    with patch("switchbot_actions.mqtt.aiomqtt.Client") as mock_client:
        yield mock_client


@pytest.fixture
def mqtt_settings():
    return MqttSettings(host="localhost", port=1883, username="user", password="pass")


def test_mqtt_client_initialization(mock_aiomqtt_client, mqtt_settings):
    MqttClient(settings=mqtt_settings)
    mock_aiomqtt_client.assert_called_once_with(
        hostname="localhost", port=1883, username="user", password="pass"
    )


@patch("switchbot_actions.mqtt.aiomqtt.Client")
@pytest.mark.asyncio
async def test_message_reception_and_signal(
    mock_aiomqtt_client, mqtt_settings, mqtt_message_plain
):
    client = MqttClient(settings=mqtt_settings)

    mock_message = mqtt_message_plain

    async def mock_message_generator():
        yield mock_message

    mock_aiomqtt_client.return_value.messages = mock_message_generator()

    received_signals = []

    def on_message_received(sender, message):
        received_signals.append(message)

    mqtt_message_received.connect(on_message_received)

    client = MqttClient(settings=mqtt_settings)

    async for message in client.client.messages:
        mqtt_message_received.send(client, message=message)

    assert len(received_signals) == 1
    assert received_signals[0].topic.value == "test/topic"
    assert received_signals[0].payload == b"ON"

    mqtt_message_received.disconnect(on_message_received)


@pytest.mark.asyncio
async def test_publish_message(mqtt_settings):
    client = MqttClient(settings=mqtt_settings)
    client.client.publish = AsyncMock()

    await client.publish("test/topic", "test_payload")

    client.client.publish.assert_called_once_with(
        "test/topic", "test_payload", qos=0, retain=False
    )


@pytest.mark.asyncio
async def test_publish_message_handles_error(mqtt_settings, caplog):
    client = MqttClient(settings=mqtt_settings)
    client.client.publish = AsyncMock(side_effect=MqttError("Test Error"))

    await client.publish("test/topic", "test_payload")

    assert "MQTT client not connected, cannot publish message." in caplog.text
