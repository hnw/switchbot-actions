import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import httpx

from .config import (
    AutomationAction,
    MqttPublishAction,
    ShellCommandAction,
    WebhookAction,
)
from .evaluator import StateObject
from .signals import publish_mqtt_message_request

T_Action = TypeVar("T_Action", bound=AutomationAction)

logger = logging.getLogger(__name__)


class ActionExecutor(ABC, Generic[T_Action]):
    """Abstract base class for action executors."""

    def __init__(self, action: T_Action):
        self.action: T_Action = action

    @abstractmethod
    async def execute(self, state: StateObject) -> None:
        """Executes the action."""
        pass


class ShellCommandExecutor(ActionExecutor):
    """Executes a shell command."""

    async def execute(self, state: StateObject) -> None:
        command = state.format(self.action.command)
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

    async def execute(self, state: StateObject) -> None:
        url = state.format(self.action.url)
        method = self.action.method
        payload = state.format(self.action.payload)
        headers = state.format(self.action.headers)

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

    async def execute(self, state: StateObject) -> None:
        topic = state.format(self.action.topic)
        qos = self.action.qos
        retain = self.action.retain

        payload = state.format(self.action.payload)

        logger.debug(
            f"Publishing MQTT message to topic '{topic}' with payload '{payload}' "
            f"(qos={qos}, retain={retain})"
        )
        publish_mqtt_message_request.send(
            None, topic=topic, payload=payload, qos=qos, retain=retain
        )


def create_action_executor(action: AutomationAction) -> ActionExecutor:
    if isinstance(action, ShellCommandAction):
        return ShellCommandExecutor(action)
    elif isinstance(action, WebhookAction):
        return WebhookExecutor(action)
    elif isinstance(action, MqttPublishAction):
        return MqttPublishExecutor(action)
    else:
        raise ValueError(f"Unknown action type: {action.type}")
