import asyncio
import sys
import threading

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.client import MQTT_ERR_SUCCESS
from paho.mqtt.enums import CallbackAPIVersion


@pytest.mark.asyncio
async def test_mqtt_to_mqtt_publish_action(config_generator):
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
    subscriber_client = None
    try:
        # 2. Set up MQTT subscriber
        subscriber_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2
        )
        subscriber_client.on_message = on_message

        # --- Start of new connection logic for subscriber_client ---
        subscriber_connect_event = threading.Event()
        subscriber_connect_result_code = -1

        def on_subscriber_connect(client, userdata, flags, rc, properties=None):
            nonlocal subscriber_connect_result_code
            subscriber_connect_result_code = rc
            subscriber_connect_event.set()

        subscriber_client.on_connect = on_subscriber_connect

        try:
            subscriber_client.connect(mqtt_broker_host, mqtt_broker_port, 60)
            subscriber_client.loop_start()  # Start network loop in a separate thread

            # Wait for the on_connect callback to be called
            if not subscriber_connect_event.wait(
                timeout=10
            ):  # 10 seconds timeout for connection
                pytest.fail(
                    f"Timed out waiting for subscriber MQTT connection to "
                    f"{mqtt_broker_host}:{mqtt_broker_port}"
                )

            if subscriber_connect_result_code != MQTT_ERR_SUCCESS:
                pytest.fail(
                    f"Failed to connect subscriber to MQTT broker at "
                    f"{mqtt_broker_host}:{mqtt_broker_port}. "
                    f"Connection refused: "
                    f"{mqtt.connack_string(subscriber_connect_result_code)}"
                )
        except Exception as e:  # Catch any other exceptions during connect/loop_start
            pytest.fail(
                f"An unexpected error occurred during subscriber MQTT connection: "
                f"{type(e).__name__} - {e}"
            )
        # --- End of new connection logic for subscriber_client ---
        result, mid = subscriber_client.subscribe(publish_topic)
        if result != mqtt.MQTT_ERR_SUCCESS:
            pytest.fail(
                f"Failed to subscribe to topic '{publish_topic}'. "
                f"MQTT error code: {result}"
            )
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
        # --- Start of new connection logic for publisher_client ---
        publisher_connect_event = threading.Event()
        publisher_connect_result_code = -1

        def on_publisher_connect(client, userdata, flags, rc, properties=None):
            nonlocal publisher_connect_result_code
            publisher_connect_result_code = rc
            publisher_connect_event.set()

        publisher_client.on_connect = on_publisher_connect

        try:
            publisher_client.connect(mqtt_broker_host, mqtt_broker_port, 60)
            publisher_client.loop_start()  # Start the network loop in a separate thread

            # Wait for the on_connect callback to be called
            if not publisher_connect_event.wait(
                timeout=10
            ):  # 10 seconds timeout for connection
                pytest.fail(
                    f"Timed out waiting for publisher MQTT connection to "
                    f"{mqtt_broker_host}:{mqtt_broker_port}"
                )

            if publisher_connect_result_code != MQTT_ERR_SUCCESS:
                pytest.fail(
                    f"Failed to connect publisher to MQTT broker at "
                    f"{mqtt_broker_host}:{mqtt_broker_port}. "
                    f"Connection refused: "
                    f"{mqtt.connack_string(publisher_connect_result_code)}"
                )
        except Exception as e:  # Catch any other exceptions during connect/loop_start
            pytest.fail(
                f"An unexpected error occurred during publisher MQTT connection: "
                f"{type(e).__name__} - {e}"
            )
        finally:
            publisher_client.loop_stop()  # Stop the network loop
        # --- End of new connection logic for publisher_client ---
        try:
            message_info = publisher_client.publish(trigger_topic, "trigger")
            message_info.wait_for_publish()
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{trigger_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )
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
