import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union, cast

import aiomqtt
from blinker import signal

from .component import BaseComponent
from .config import MqttSettings

logger = logging.getLogger(__name__)
mqtt_message_received = signal("mqtt-message-received")


class _NullClient:
    """A dummy client that does nothing. Used before the real client is started."""

    async def publish(self, *args, **kwargs):
        logger.debug("MQTT client is not connected. Publish request ignored.")
        await asyncio.sleep(0)  # Yield control to the event loop


_null_client = _NullClient()


class MqttClient(BaseComponent[MqttSettings]):
    def __init__(self, settings: MqttSettings):
        super().__init__(settings)
        # Initialize with the null client. The real client is created in _start.
        self.client: Union[aiomqtt.Client, _NullClient] = _null_client
        self._stop_event = asyncio.Event()
        self._mqtt_loop_task: asyncio.Task | None = None

    def _is_enabled(self, settings: Optional[MqttSettings] = None) -> bool:
        """Checks if the component is enabled based on current or new settings."""
        current_settings = settings or self.settings
        return current_settings.enabled

    async def _start(self):
        logger.info("Starting MQTT client.")
        # Replace the null client with the real one.
        self.client = aiomqtt.Client(
            hostname=self.settings.host,
            port=self.settings.port,
            username=self.settings.username,
            password=self.settings.password,
        )
        self._mqtt_loop_task = asyncio.create_task(self._run_mqtt_loop())

    async def _run_mqtt_loop(self):
        # This loop is only started after the real client is created in _start().
        # We can safely assume self.client is a real aiomqtt.Client here.
        real_client = cast(aiomqtt.Client, self.client)
        while not self._stop_event.is_set():
            try:
                # The async context manager is on the real client instance.
                async with real_client as client:
                    await self._subscribe_to_topics(client)
                    logger.info("MQTT client connected and subscribed.")
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

    async def _stop(self):
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
        # Replace the real client with the null client again for a clean state.
        self.client = _null_client

    def _require_restart(self, new_settings: MqttSettings) -> bool:
        """
        Determines if a restart is required for the MQTT client based on new settings.
        A restart is required if host, port, username, or password changes.
        """
        return (
            self.settings.host != new_settings.host
            or self.settings.port != new_settings.port
            or self.settings.username != new_settings.username
            or self.settings.password != new_settings.password
        )

    async def _apply_live_update(self, new_settings: MqttSettings) -> None:
        """
        Applies live updates to MQTT client settings (e.g., reconnect_interval).
        Changes picked up by MQTT loop in next reconnection attempt.
        """
        # The _run_mqtt_loop directly references self.settings.reconnect_interval.
        # By updating self.settings in apply_new_settings (in BaseComponent),
        # the loop will automatically use the new value in its next reconnection.
        # No explicit action is needed here.
        pass

    async def _subscribe_to_topics(self, client: aiomqtt.Client):
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
            await self.client.publish(topic, str(payload), qos=qos, retain=retain)
        except aiomqtt.MqttError:
            logger.warning("MQTT client not connected, cannot publish message.")
