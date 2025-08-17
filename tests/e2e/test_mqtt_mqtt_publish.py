import asyncio
import sys

import paho.mqtt.client as mqtt
import pytest


@pytest.mark.asyncio
async def test_mqtt_to_mqtt_publish_action(config_generator, mqtt_client):
    mqtt_broker_host = "127.0.0.1"
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
        "scanner": {
            "enabled": False,
        },
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
    try:
        # 2. Set up MQTT subscriber
        mqtt_client.on_message = on_message

        result, mid = mqtt_client.subscribe(publish_topic)
        if result != mqtt.MQTT_ERR_SUCCESS:
            pytest.fail(
                f"Failed to subscribe to topic '{publish_topic}'. "
                f"MQTT error code: {result}"
            )

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
        try:
            message_info = mqtt_client.publish(trigger_topic, "trigger")
            message_info.wait_for_publish()
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{trigger_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )

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
