import asyncio
import logging

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

    async def run(self):
        while True:
            try:
                async with self.client:
                    await self._subscribe_to_topics()
                    logger.info("MQTT client connected.")
                    async for message in self.client.messages:
                        mqtt_message_received.send(self, message=message)
            except aiomqtt.MqttError as error:
                logger.error(
                    f"MQTT error: {error}. "
                    f"Reconnecting in {self.settings.reconnect_interval} seconds."
                )
                await asyncio.sleep(self.settings.reconnect_interval)
            finally:
                logger.info("MQTT client disconnected.")

    async def _subscribe_to_topics(self):
        # At the moment, we subscribe to all topics.
        # In the future, we may want to subscribe to specific topics based on the rules.
        await self.client.subscribe("#")

    async def publish(
        self, topic: str, payload: str, qos: int = 0, retain: bool = False
    ):
        try:
            await self.client.publish(topic, payload, qos=qos, retain=retain)
        except aiomqtt.MqttError:
            logger.warning("MQTT client not connected, cannot publish message.")
