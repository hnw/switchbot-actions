import asyncio
import json
from typing import cast
from unittest.mock import AsyncMock, patch

import aiomqtt
import pytest

from switchbot_actions.config import MqttSettings
from switchbot_actions.mqtt import MqttClient, mqtt_message_received


@pytest.fixture
def mock_aiomqtt_client():
    with patch("switchbot_actions.mqtt.aiomqtt.Client") as mock_client:
        yield mock_client


@pytest.fixture
def mqtt_settings():
    return MqttSettings(
        enabled=True, host="localhost", port=1883, username="user", password="pass"
    )


def test_mqtt_client_initialization(mock_aiomqtt_client, mqtt_settings):
    MqttClient(settings=mqtt_settings)
    # Initialization now uses a null object, so the real client is not called here.
    mock_aiomqtt_client.assert_not_called()


@pytest.mark.asyncio
async def test_start_creates_real_client(mock_aiomqtt_client, mqtt_settings):
    """Test that start() creates and uses the real aiomqtt.Client."""
    client = MqttClient(settings=mqtt_settings)
    # Make the loop exit immediately after starting
    client._run_mqtt_loop = AsyncMock()

    await client.start()

    mock_aiomqtt_client.assert_called_once_with(
        hostname="localhost", port=1883, username="user", password="pass"
    )
    assert client._mqtt_loop_task is not None
    await client.stop()


@pytest.mark.asyncio
async def test_message_reception_and_signal(mqtt_settings, mqtt_message_plain):
    """
    Tests that the MqttClient component correctly receives messages from the
    broker and emits a `mqtt_message_received` signal.
    """
    # 1. Setup: Create a mock aiomqtt.Client that will yield a test message.
    mock_instance = AsyncMock(spec=aiomqtt.Client)

    async def mock_messages_generator():
        yield mqtt_message_plain
        # Keep the loop running until cancelled to simulate a real connection
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

    # Configure the mock instance's async context manager and message iterator
    mock_instance.messages = mock_messages_generator()  # Correctly assign the iterator
    mock_instance.__aenter__.return_value = mock_instance  # __aenter__ returns self

    # 2. Patch the aiomqtt.Client constructor to return our mock instance
    with patch("switchbot_actions.mqtt.aiomqtt.Client", return_value=mock_instance):
        # 3. Setup signal receiver
        received_signals = []
        received_event = asyncio.Event()

        def on_message_received(sender, message):
            received_signals.append(message)
            received_event.set()

        mqtt_message_received.connect(on_message_received)

        # 4. Action: Instantiate and start the MqttClient component
        client = MqttClient(settings=mqtt_settings)
        await client.start()

        # 5. Assert: Wait for the signal to be received
        try:
            await asyncio.wait_for(received_event.wait(), timeout=1)
        except asyncio.TimeoutError:
            pytest.fail("mqtt_message_received signal was not emitted within timeout.")
        finally:
            # 6. Cleanup
            await client.stop()
            mqtt_message_received.disconnect(on_message_received)

        # 7. Final assertions on the received signal data
        assert len(received_signals) == 1
        assert received_signals[0].topic.value == "test/topic"
        assert received_signals[0].payload == b"ON"


@pytest.mark.asyncio
async def test_publish_message_for_null_client(mqtt_settings):
    client = MqttClient(settings=mqtt_settings)
    # Since the client is not started, it should use the _NullClient
    client.client.publish = AsyncMock()
    await client.publish("test/topic", "test_payload")
    client.client.publish.assert_called_once_with(
        "test/topic", "test_payload", qos=0, retain=False
    )


@pytest.mark.asyncio
async def test_publish_message(mqtt_settings):
    client = MqttClient(settings=mqtt_settings)
    client._run_mqtt_loop = AsyncMock()
    await client.start()
    client.client.publish = AsyncMock()
    await client.publish("test/topic", "test_payload")
    client.client.publish.assert_called_once_with(
        "test/topic", "test_payload", qos=0, retain=False
    )
    await client.stop()


@pytest.mark.asyncio
async def test_publish_message_handles_error(mqtt_settings, caplog):
    client = MqttClient(settings=mqtt_settings)
    # Start the client to use the real aiomqtt.Client
    client._run_mqtt_loop = AsyncMock()  # Prevent loop from running
    await client.start()
    # Manually set the real client's publish to an async mock that raises an error
    real_client = cast(aiomqtt.Client, client.client)
    real_client.publish = AsyncMock(side_effect=aiomqtt.MqttError("Test Error"))

    await client.publish("test/topic", "test_payload")

    assert "MQTT client not connected, cannot publish message." in caplog.text
    await client.stop()


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
        mock_instance.__aenter__.return_value = mock_instance

        async def mock_subscribe(*args, **kwargs):
            subscribed_event.set()

        mock_instance.subscribe = AsyncMock(side_effect=mock_subscribe)

        async def mock_messages_generator():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
            if False:
                yield

        mock_instance.messages = mock_messages_generator()

        client = MqttClient(settings=mqtt_settings)
        await client.start()

        try:
            await asyncio.wait_for(subscribed_event.wait(), timeout=1)
        except asyncio.TimeoutError:
            pytest.fail("Subscribe was not called within the timeout period.")
        finally:
            await client.stop()

        mock_instance.subscribe.assert_awaited_once_with("#")
        assert client._mqtt_loop_task is None


@pytest.mark.asyncio
async def test_mqtt_client_reconnect_on_failure(mqtt_settings, caplog):
    """
    Tests that the client attempts to reconnect after a connection failure.
    """
    client = MqttClient(settings=mqtt_settings)
    client.settings.reconnect_interval = 0.01

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
        mock_aiomqtt_client.return_value.__aenter__.side_effect = aiomqtt.MqttError(
            "Connection failed"
        )
        mock_sleep.side_effect = TestBreakLoop()

        # We need to manually set the client to a real mock instance for this test
        client.client = mock_aiomqtt_client.return_value

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
    client._run_mqtt_loop = AsyncMock()
    await client.start()
    client.client.publish = AsyncMock()

    payload_dict = {"key": "value", "number": 123}
    expected_json_string = json.dumps(payload_dict)

    await client.publish("test/json_topic", payload_dict)

    client.client.publish.assert_called_once_with(
        "test/json_topic", expected_json_string, qos=0, retain=False
    )
    await client.stop()


@pytest.mark.asyncio
async def test_start_does_not_call__start_if_disabled():
    """
    Tests that the public start() method does not call the internal _start()
    if the component is disabled via its settings.
    """
    disabled_settings = MqttSettings(enabled=False)  # pyright:ignore[reportCallIssue]
    client = MqttClient(settings=disabled_settings)

    client._start = AsyncMock()

    await client.start()

    client._start.assert_not_called()


# --- Added Tests for Reload Logic ---


@pytest.mark.parametrize("setting_to_change", ["host", "port", "username", "password"])
def test_require_restart_on_critical_settings_change(mqtt_settings, setting_to_change):
    """
    Tests that _require_restart returns True when critical connection
    settings are changed.
    """
    client = MqttClient(settings=mqtt_settings)
    new_settings = mqtt_settings.model_copy()

    # Change one of the critical settings
    setattr(new_settings, setting_to_change, "new_value")

    assert client._require_restart(new_settings) is True


def test_no_restart_on_non_critical_settings_change(mqtt_settings):
    """
    Tests that _require_restart returns False when a non-critical setting
    like reconnect_interval is changed.
    """
    client = MqttClient(settings=mqtt_settings)
    new_settings = mqtt_settings.model_copy()

    # Change a non-critical setting
    new_settings.reconnect_interval = 999

    assert client._require_restart(new_settings) is False
