import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from .config import (
    AutomationAction,
    MqttPublishAction,
    ShellCommandAction,
    WebhookAction,
)
from .evaluator import StateObject, format_object, format_string
from .signals import publish_mqtt_message_request

logger = logging.getLogger(__name__)


class ActionExecutor(ABC):
    """Abstract base class for action executors."""

    def __init__(self, action: AutomationAction):
        self.action = action

    @abstractmethod
    async def execute(self, state: StateObject) -> None:
        """Executes the action."""
        pass


class ShellCommandExecutor(ActionExecutor):
    """Executes a shell command."""

    def __init__(self, action: ShellCommandAction):
        super().__init__(action)
        self.action: ShellCommandAction

    async def execute(self, state: StateObject) -> None:
        command = format_string(self.action.command, state)
        logger.debug(f"Executing shell command: {command}")
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if stdout:
            logger.debug(f"Shell command stdout: {stdout.decode().strip()}")
        if stderr:
            logger.error(f"Shell command stderr: {stderr.decode().strip()}")
        if process.returncode != 0:
            logger.error(f"Shell command failed with exit code {process.returncode}")


class WebhookExecutor(ActionExecutor):
    """Sends a webhook."""

    def __init__(self, action: WebhookAction):
        super().__init__(action)
        self.action: WebhookAction

    async def execute(self, state: StateObject) -> None:
        url = format_string(self.action.url, state)
        method = self.action.method
        payload = format_object(self.action.payload, state)
        headers = format_object(self.action.headers, state)

        logger.debug(
            f"Sending webhook: {method} {url} with payload {payload} "
            f"and headers {headers}"
        )
        await self._send_request(url, method, payload, headers)

    async def _send_request(
        self, url: str, method: str, payload: dict | str, headers: dict
    ) -> None:
        try:
            async with httpx.AsyncClient() as client:
                if method == "POST":
                    response = await client.post(
                        url, json=payload, headers=headers, timeout=10
                    )
                elif method == "GET":
                    response = await client.get(
                        url, params=payload, headers=headers, timeout=10
                    )
                else:
                    logger.error(f"Unsupported HTTP method for webhook: {method}")
                    return

                if 200 <= response.status_code < 300:
                    logger.debug(
                        f"Webhook to {url} successful with status "
                        f"{response.status_code}"
                    )
                else:
                    response_body_preview = (
                        response.text[:200] if response.text else "(empty)"
                    )
                    logger.error(
                        f"Webhook to {url} failed with status {response.status_code}. "
                        f"Response: {response_body_preview}"
                    )
        except httpx.RequestError as e:
            logger.error(f"Webhook failed: {e}")


class MqttPublishExecutor(ActionExecutor):
    """Publishes an MQTT message."""

    def __init__(self, action: MqttPublishAction):
        super().__init__(action)
        self.action: MqttPublishAction

    async def execute(self, state: StateObject) -> None:
        topic = format_string(self.action.topic, state)
        qos = self.action.qos
        retain = self.action.retain

        payload = format_object(self.action.payload, state)

        logger.debug(
            f"Publishing MQTT message to topic '{topic}' with payload '{payload}' "
            f"(qos={qos}, retain={retain})"
        )
        publish_mqtt_message_request.send(
            None, topic=topic, payload=payload, qos=qos, retain=retain
        )
