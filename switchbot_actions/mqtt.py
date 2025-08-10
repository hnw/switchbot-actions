import asyncio
import json
import logging
from typing import Any, Dict, Union

import aiomqtt
from blinker import signal

from .config import MqttSettings

logger = logging.getLogger(__name__)
mqtt_message_received = signal("mqtt-message-received")


class MqttClient:
    def __init__(self, settings: MqttSettings):
        self.settings = settings
        self.client = aiomqtt.Client(
            hostname=self.settings.host,
            port=self.settings.port,
            username=self.settings.username,
            password=self.settings.password,
        )
        self._stop_event = asyncio.Event()
        self._mqtt_loop_task: asyncio.Task | None = None

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def start(self):
        logger.info("Starting MQTT client.")
        self._mqtt_loop_task = asyncio.create_task(self._run_mqtt_loop())

    async def _run_mqtt_loop(self):
        while not self._stop_event.is_set():
            try:
                async with self as client:
                    await self._subscribe_to_topics(client)
                    logger.info("MQTT client connected.")
                    async for message in client.messages:
                        mqtt_message_received.send(self, message=message)
            except aiomqtt.MqttError as error:
                logger.error(
                    f"MQTT error: {error}. "
                    f"Reconnecting in {self.settings.reconnect_interval} seconds."
                )
                await asyncio.sleep(self.settings.reconnect_interval)
            except asyncio.CancelledError:
                logger.info("MQTT client loop task successfully cancelled.")
                break
            finally:
                logger.info("MQTT client disconnected.")

    async def stop(self):
        logger.info("Stopping MQTT client.")
        self._stop_event.set()
        if self._mqtt_loop_task and not self._mqtt_loop_task.done():
            self._mqtt_loop_task.cancel()
            try:
                await self._mqtt_loop_task
            except asyncio.CancelledError:
                logger.info(
                    "MQTT client loop task successfully awaited after cancellation."
                )
        self._mqtt_loop_task = None

    async def _subscribe_to_topics(self, client: aiomqtt.Client):
        # At the moment, we subscribe to all topics.
        # In the future, we may want to subscribe to specific topics based on the rules.
        await client.subscribe("#")

    async def publish(
        self,
        topic: str,
        payload: Union[str, Dict[str, Any]],
        qos: int = 0,
        retain: bool = False,
    ):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        try:
            await self.client.publish(topic, payload, qos=qos, retain=retain)
        except aiomqtt.MqttError:
            logger.warning("MQTT client not connected, cannot publish message.")
