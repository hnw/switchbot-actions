import asyncio
import sys

import pytest

# Run switchbot-actions via CLI with config


@pytest.mark.asyncio
async def test_mqtt_to_log_action(config_generator, mqtt_client):
    mqtt_broker_host = "127.0.0.1"
    mqtt_broker_port = 1883
    mqtt_topic = "test/log"
    expected_log_message = "Hello from MQTT log!"

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
                        "type": "log",
                        "message": expected_log_message,
                    }
                ],
            }
        ],
    }
    config_path = config_generator(config_content)

    # 2. Run switchbot-actions in a subprocess and capture stdout
    process = None

    try:
        # Start the switchbot-actions application
        # We need to ensure the application logs to stdout for this test
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

        # Give the application some time to start up and connect to MQTT
        await asyncio.sleep(5)

        # 3. Publish MQTT message
        try:
            message_info = mqtt_client.publish(mqtt_topic, "trigger")
            message_info.wait_for_publish(timeout=3)
        except Exception as e:
            pytest.fail(
                f"Failed to publish message to topic '{mqtt_topic}'. "
                f"Error: {type(e).__name__} - {e}"
            )

        # Give some time for the action to be processed and logged
        await asyncio.sleep(5)

        # 4. Read stdout and verify log message
        if process.returncode is None:
            process.terminate()

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

        assert any(expected_log_message in line for line in stdout_lines), (
            f"Expected log message '{expected_log_message}' not found in stdout."
        )

    finally:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
