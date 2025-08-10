import asyncio
import json
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


@pytest.mark.asyncio
async def test_mqtt_client_lifecycle_and_subscription(mqtt_settings):
    """
    Tests that the client starts, subscribes to topics, and stops gracefully.
    """
    subscribed_event = asyncio.Event()

    with patch(
        "switchbot_actions.mqtt.aiomqtt.Client", autospec=True
    ) as mock_aiomqtt_client:
        mock_instance = mock_aiomqtt_client.return_value

        # Mock `subscribe` to set an event when it's called
        async def mock_subscribe(*args, **kwargs):
            subscribed_event.set()

        mock_instance.subscribe = AsyncMock(side_effect=mock_subscribe)

        # Make the `messages` async iterator block indefinitely until cancelled
        async def mock_messages_generator():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
            # The 'if False' makes this yield unreachable, but it's necessary
            # to tell Python that this is an async generator, not a coroutine.
            if False:
                yield

        mock_instance.messages.__aiter__.return_value = mock_messages_generator()

        client = MqttClient(settings=mqtt_settings)
        await client.start()  # This starts _run_mqtt_loop in the background

        try:
            # Wait for the subscribe call to happen, with a timeout
            await asyncio.wait_for(subscribed_event.wait(), timeout=1)
        except asyncio.TimeoutError:
            pytest.fail("Subscribe was not called within the timeout period.")
        finally:
            # Ensure cleanup by stopping the client
            await client.stop()

        # Assert that subscribe was called correctly
        mock_instance.subscribe.assert_awaited_once_with("#")
        # Assert that the background task was cleaned up
        assert client._mqtt_loop_task is None


@pytest.mark.asyncio
async def test_mqtt_client_reconnect_on_failure(mqtt_settings, caplog):
    """
    Tests that the client attempts to reconnect after a connection failure.
    """
    client = MqttClient(settings=mqtt_settings)
    client.settings.reconnect_interval = 0.01  # Use a small interval for testing

    # Custom exception to break the infinite loop for the test
    class TestBreakLoop(Exception):
        pass

    with (
        patch(
            "switchbot_actions.mqtt.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep,
        patch(
            "switchbot_actions.mqtt.aiomqtt.Client", autospec=True
        ) as mock_aiomqtt_client,
    ):
        # Configure the async with block to raise MqttError
        mock_aiomqtt_client.return_value.__aenter__.side_effect = MqttError(
            "Connection failed"
        )
        # Make sleep raise an exception to break the loop after one iteration
        mock_sleep.side_effect = TestBreakLoop()

        # The loop will run, fail, log, and then our mocked sleep will raise to exit.
        with pytest.raises(TestBreakLoop):
            await client._run_mqtt_loop()

        assert "MQTT error" in caplog.text
        assert "Reconnecting in" in caplog.text
        mock_sleep.assert_awaited_once_with(client.settings.reconnect_interval)


@pytest.mark.asyncio
async def test_publish_json_payload(mqtt_settings):
    """
    Tests that a dictionary payload is correctly serialized to a JSON string.
    """
    client = MqttClient(settings=mqtt_settings)
    client.client.publish = AsyncMock()

    payload_dict = {"key": "value", "number": 123}
    expected_json_string = json.dumps(payload_dict)

    await client.publish("test/json_topic", payload_dict)

    client.client.publish.assert_called_once_with(
        "test/json_topic", expected_json_string, qos=0, retain=False
    )
