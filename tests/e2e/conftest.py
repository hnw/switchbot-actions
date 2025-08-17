import json
import threading

import paho.mqtt.client as mqtt
import pytest
import pytest_asyncio
import yaml
from aiohttp import web
from paho.mqtt.client import MQTT_ERR_SUCCESS
from paho.mqtt.enums import CallbackAPIVersion


@pytest_asyncio.fixture
async def webhook_server():
    """
    Fixture for a simple aiohttp webhook server.
    It captures the last received request.
    """
    app = web.Application()
    received_requests = []

    async def handler(request):
        data = None
        if request.can_read_body:
            try:
                data = await request.json()
            except json.JSONDecodeError:
                data = await request.text()
        received_requests.append(
            {
                "method": request.method,
                "headers": dict(request.headers),
                "path": request.path,
                "query": dict(request.query),
                "body": data,
            }
        )
        return web.Response(text="OK")

    app.router.add_route("*", "/webhook", handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8080)
    await site.start()

    yield received_requests

    await runner.cleanup()


@pytest.fixture
def config_generator(tmp_path):
    """
    Fixture to generate dynamic config.yaml files for tests.
    """

    def _generate_config(config_content: dict):
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_content, f)
        return config_path

    return _generate_config


@pytest.fixture
def mqtt_client():
    """
    Fixture for a connected MQTT client.
    Connects to the broker, yields the client, and disconnects on teardown.
    """
    mqtt_broker_host = "127.0.0.1"
    mqtt_broker_port = 1883

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)

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
        yield client
    except Exception as e:
        pytest.fail(
            f"An unexpected error occurred during MQTT connection: "
            f"{type(e).__name__} - {e}"
        )
    finally:
        client.loop_stop()
        client.disconnect()
