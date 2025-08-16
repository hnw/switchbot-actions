import asyncio
import sys

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion


@pytest.mark.asyncio
async def test_mqtt_to_mqtt_publish_action(config_generator):
    mqtt_broker_host = "localhost"
    mqtt_broker_port = 1883
    trigger_topic = "test/trigger_publish"
    publish_topic = "test/published_message"
    expected_payload = "Hello from MQTT Publish!"

    received_message = None
    message_received_event = asyncio.Event()

    def on_message(client, userdata, msg):
        nonlocal received_message
        received_message = msg.payload.decode()
        message_received_event.set()

    # 1. Generate config file
    config_content = {
        "mqtt": {
            "enabled": True,
            "host": mqtt_broker_host,
            "port": mqtt_broker_port,
        },
        "automations": [
            {
                "if": {
                    "source": "mqtt",
                    "topic": trigger_topic,
                },
                "then": [
                    {
                        "type": "mqtt_publish",
                        "topic": publish_topic,
                        "payload": expected_payload,
                    }
                ],
            }
        ],
    }
    config_path = config_generator(config_content)

    process = None
    subscriber_client = None
    try:
        # 2. Set up MQTT subscriber
        subscriber_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2
        )
        subscriber_client.on_message = on_message
        subscriber_client.connect(mqtt_broker_host, mqtt_broker_port, 60)
        subscriber_client.subscribe(publish_topic)
        subscriber_client.loop_start()  # Start non-blocking loop

        # 3. Run switchbot-actions in a subprocess
        command = [
            sys.executable,
            "-m",
            "switchbot_actions.cli",
            "--config",
            str(config_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Give the application some time to start up and connect to MQTT
        await asyncio.sleep(5)

        # 4. Publish MQTT message to trigger topic
        publisher_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        publisher_client.connect(mqtt_broker_host, mqtt_broker_port, 60)
        publisher_client.publish(trigger_topic, "trigger")
        publisher_client.disconnect()

        # 5. Wait for the message to be received by the subscriber
        try:
            await asyncio.wait_for(message_received_event.wait(), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail("Timeout waiting for MQTT published message.")

        # 6. Verify the received message
        assert received_message == expected_payload, (
            f"Expected '{expected_payload}' but received '{received_message}'"
        )

    finally:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        if subscriber_client:
            subscriber_client.loop_stop()
            subscriber_client.disconnect()
