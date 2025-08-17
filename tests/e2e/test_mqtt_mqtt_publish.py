import asyncio
import sys

import pytest

from .helpers import wait_for_log, wait_for_mqtt_message


@pytest.mark.asyncio
async def test_mqtt_to_mqtt_publish_action(config_generator, mqtt_client):
    mqtt_broker_host = "127.0.0.1"
    mqtt_broker_port = 1883
    trigger_topic = "test/trigger_publish"
    publish_topic = "test/published_message"
    expected_payload = "Hello from MQTT Publish!"
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
        # 2. Run switchbot-actions in a subprocess
        command = [
            sys.executable,
            "-m",
            "switchbot_actions.cli",
            "-vv",
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

        # 3. Start listening for the result message in the background FIRST.
        #    `create_task` starts the coroutine immediately.
        listener_task = asyncio.create_task(
            wait_for_mqtt_message(mqtt_client, publish_topic)
        )

        # Give the subscriber a moment to establish
        await asyncio.sleep(0.1)

        # 4. Now, publish the trigger message.
        try:
            message_info = mqtt_client.publish(trigger_topic, "trigger")
            message_info.wait_for_publish()
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{trigger_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )

        # 5. Finally, wait for the listener task to complete and get the payload.
        received_payload = await listener_task

        # 6. Verify the received message
        assert received_payload is not None
        assert received_payload.decode() == expected_payload, (
            f"Expected '{expected_payload}' but received '{received_payload.decode()}'"
        )

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
