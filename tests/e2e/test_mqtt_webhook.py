import asyncio
import sys

import pytest

from .helpers import wait_for_log, wait_for_webhook


@pytest.mark.asyncio
async def test_mqtt_to_webhook_action(config_generator, webhook_server, mqtt_client):
    mqtt_broker_host = "127.0.0.1"
    mqtt_broker_port = 1883
    mqtt_topic = "test/webhook"
    webhook_url = "http://localhost:8080/webhook"
    expected_webhook_payload = {"status": "triggered", "source": "mqtt"}
    app_ready_log = "MQTT client connected and subscribed."

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
            "-vv",  # Verbose logging to ensure we get the ready message
            "--config",
            str(config_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for the application to be ready
        await wait_for_log(process, app_ready_log)

        # 3. Start waiting for the webhook in the background
        webhook_task = asyncio.create_task(wait_for_webhook(webhook_server))

        # 4. Publish the MQTT trigger message
        try:
            message_info = mqtt_client.publish(mqtt_topic, "trigger")
            message_info.wait_for_publish()
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{mqtt_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )

        # 5. Wait for the webhook task to complete
        await webhook_task

        # 6. Verify webhook server received the request
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

        if process:
            stdout_data, stderr_data = await process.communicate()
            stdout_lines = stdout_data.decode().splitlines()
            stderr_lines = stderr_data.decode().splitlines()

            print("\n--- switchbot-actions stdout ---")
            for line in stdout_lines:
                print(line)
            print("--- End stdout ---\n")

            print("\n--- switchbot-actions stderr ---")
            for line in stderr_lines:
                print(line)
            print("--- End stderr ---\n")
