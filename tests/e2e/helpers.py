import asyncio

import pytest


async def wait_for_log(process, log_message, timeout=10):
    """Wait for a specific log message in the process's stdout/stderr."""
    try:

        async def _read_stream():
            streams = [process.stdout, process.stderr]
            while True:
                for stream in streams:
                    try:
                        line = await asyncio.wait_for(stream.readline(), timeout=0.1)
                        if not line:
                            continue
                        decoded_line = line.decode().strip()
                        # print(f"LOG: {decoded_line}") # Uncomment for debugging
                        if log_message in decoded_line:
                            return
                    except asyncio.TimeoutError:
                        continue

        await asyncio.wait_for(_read_stream(), timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(
            f"Timeout waiting for log message: '{log_message}' after {timeout}s"
        )


async def wait_for_webhook(webhook_server, request_count=1, timeout=10):
    """Wait for a specific number of webhook requests to be received."""
    try:

        async def _check_webhook():
            while True:
                if len(webhook_server) >= request_count:
                    return
                await asyncio.sleep(0.1)

        await asyncio.wait_for(_check_webhook(), timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"Timeout waiting for {request_count} webhook(s) after {timeout}s")


async def wait_for_mqtt_message(mqtt_client, topic, timeout=10):
    """Wait for an MQTT message on a specific topic."""
    received_event = asyncio.Event()
    received_payload = None

    def on_message(client, userdata, msg):
        nonlocal received_payload
        if msg.topic == topic:
            received_payload = msg.payload
            received_event.set()

    # Temporarily override the on_message handler
    original_on_message = mqtt_client.on_message
    mqtt_client.on_message = on_message
    mqtt_client.subscribe(topic)

    try:
        await asyncio.wait_for(received_event.wait(), timeout=timeout)
        return received_payload
    except asyncio.TimeoutError:
        pytest.fail(
            f"Timeout waiting for MQTT message on topic '{topic}' after {timeout}s"
        )
    finally:
        # Restore original handler and unsubscribe
        mqtt_client.on_message = original_on_message
        mqtt_client.unsubscribe(topic)
