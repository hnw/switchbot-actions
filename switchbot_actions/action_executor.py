import asyncio
import json
import logging

import httpx

from .config import (
    AutomationAction,
    MqttPublishAction,
    ShellCommandAction,
    WebhookAction,
)
from .evaluator import StateObject, format_string
from .signals import publish_mqtt_message_request

logger = logging.getLogger(__name__)


async def execute_action(action: AutomationAction, state: StateObject) -> None:
    """Executes the specified action (e.g., shell command, webhook)."""
    action_type = action.type

    if isinstance(action, ShellCommandAction):
        await _execute_shell_command(action, state)
    elif isinstance(action, WebhookAction):
        await _execute_webhook(action, state)
    elif isinstance(action, MqttPublishAction):
        _execute_mqtt_publish(action, state)
    else:
        logger.warning(f"Unknown trigger type: {action_type}")


async def _execute_shell_command(
    action: ShellCommandAction, state: StateObject
) -> None:
    command = format_string(action.command, state)
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


async def _execute_webhook(action: WebhookAction, state: StateObject) -> None:
    url = format_string(action.url, state)
    method = action.method

    # Format payload
    if isinstance(action.payload, dict):
        payload = {k: format_string(str(v), state) for k, v in action.payload.items()}
    else:
        payload = format_string(str(action.payload), state)

    # Format headers
    headers = {k: format_string(str(v), state) for k, v in action.headers.items()}

    logger.debug(
        f"Sending webhook: {method} {url} with payload {payload} and headers {headers}"
    )
    await _send_webhook_request(url, method, payload, headers)


async def _send_webhook_request(
    url: str, method: str, payload: dict | str, headers: dict
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
                    f"Webhook to {url} successful with status {response.status_code}"
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


def _execute_mqtt_publish(action: MqttPublishAction, state: StateObject) -> None:
    topic = format_string(action.topic, state)
    qos = action.qos
    retain = action.retain

    if isinstance(action.payload, dict):
        formatted_payload = {
            k: format_string(str(v), state) for k, v in action.payload.items()
        }
        payload = json.dumps(formatted_payload)
    else:
        payload = format_string(str(action.payload), state)

    logger.debug(
        f"Publishing MQTT message to topic '{topic}' with payload '{payload}' "
        f"(qos={qos}, retain={retain})"
    )
    publish_mqtt_message_request.send(
        None, topic=topic, payload=payload, qos=qos, retain=retain
    )
