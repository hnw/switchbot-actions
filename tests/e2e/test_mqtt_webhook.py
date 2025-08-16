import asyncio
import sys
import threading

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.client import MQTT_ERR_SUCCESS
from paho.mqtt.enums import CallbackAPIVersion


@pytest.mark.asyncio
async def test_mqtt_to_webhook_action(config_generator, webhook_server):
    mqtt_broker_host = "127.0.0.1"
    mqtt_broker_port = 1883
    mqtt_topic = "test/webhook"
    webhook_url = "http://localhost:8080/webhook"
    expected_webhook_payload = {"status": "triggered", "source": "mqtt"}

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
                    "topic": mqtt_topic,
                },
                "then": [
                    {
                        "type": "webhook",
                        "url": webhook_url,
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "payload": expected_webhook_payload,
                    }
                ],
            }
        ],
    }
    config_path = config_generator(config_content)

    process = None
    try:
        # 2. Run switchbot-actions in a subprocess
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

        # 3. Publish MQTT message
        client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        # --- Start of new connection logic ---
        connect_event = threading.Event()
        connect_result_code = -1

        def on_connect(client, userdata, flags, rc, properties=None):
            nonlocal connect_result_code
            connect_result_code = rc
            connect_event.set()

        client.on_connect = on_connect

        try:
            client.connect(mqtt_broker_host, mqtt_broker_port, 60)
            client.loop_start()  # Start the network loop in a separate thread

            # Wait for the on_connect callback to be called
            if not connect_event.wait(timeout=10):  # 10 seconds timeout for connection
                pytest.fail(
                    f"Timed out waiting for MQTT connection to "
                    f"{mqtt_broker_host}:{mqtt_broker_port}"
                )

            if connect_result_code != MQTT_ERR_SUCCESS:
                pytest.fail(
                    f"Failed to connect to MQTT broker at "
                    f"{mqtt_broker_host}:{mqtt_broker_port}. "
                    f"Connection refused: {mqtt.connack_string(connect_result_code)}"
                )
        except Exception as e:  # Catch any other exceptions during connect/loop_start
            pytest.fail(
                f"An unexpected error occurred during MQTT connection: "
                f"{type(e).__name__} - {e}"
            )
        finally:
            client.loop_stop()  # Stop the network loop
        # --- End of new connection logic ---
        try:
            message_info = client.publish(mqtt_topic, "trigger")
            message_info.wait_for_publish()
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{mqtt_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )
        client.disconnect()

        # Give some time for the action to be processed and webhook to be sent
        await asyncio.sleep(5)

        # 4. Verify webhook server received the request
        assert len(webhook_server) == 1, (
            "Webhook server received incorrect number of requests."
        )
        received_request = webhook_server[0]

        assert received_request["method"] == "POST"
        assert received_request["path"] == "/webhook"
        assert received_request["headers"].get("Content-Type") == "application/json"
        assert received_request["body"] == expected_webhook_payload

    finally:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
