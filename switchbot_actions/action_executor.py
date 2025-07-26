import asyncio
import json
import logging

import httpx

from .evaluator import StateObject, format_string
from .signals import publish_mqtt_message_request

logger = logging.getLogger(__name__)


async def execute_action(action: dict, state: StateObject) -> None:
    """Executes the specified action (e.g., shell command, webhook)."""
    action_type = action.get("type")

    if action_type == "shell_command":
        await _execute_shell_command(action, state)
    elif action_type == "webhook":
        await _execute_webhook(action, state)
    elif action_type == "mqtt_publish":
        await _execute_mqtt_publish(action, state)
    else:
        logger.warning(f"Unknown trigger type: {action_type}")


async def _execute_shell_command(action: dict, state: StateObject) -> None:
    command = format_string(action["command"], state)
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


async def _execute_webhook(action: dict, state: StateObject) -> None:
    url = format_string(action["url"], state)
    method = action.get("method", "POST").upper()
    payload = action.get("payload", {})
    headers = action.get("headers", {})

    # Format payload
    if isinstance(payload, dict):
        formatted_payload = {
            k: format_string(str(v), state) for k, v in payload.items()
        }
    else:
        formatted_payload = format_string(str(payload), state)

    # Format headers
    formatted_headers = {k: format_string(str(v), state) for k, v in headers.items()}

    logger.debug(
        f"Sending webhook: {method} {url} with payload {formatted_payload} "
        f"and headers {formatted_headers}"
    )
    try:
        async with httpx.AsyncClient() as client:
            if method == "POST":
                response = await client.post(
                    url, json=formatted_payload, headers=formatted_headers, timeout=10
                )
            elif method == "GET":
                response = await client.get(
                    url, params=formatted_payload, headers=formatted_headers, timeout=10
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


async def _execute_mqtt_publish(action: dict, state: StateObject) -> None:
    topic = format_string(action["topic"], state)
    payload_config = action.get("payload", "")
    qos = action.get("qos", 0)
    retain = action.get("retain", False)

    if isinstance(payload_config, dict):
        formatted_payload = {
            k: format_string(str(v), state) for k, v in payload_config.items()
        }
        payload = json.dumps(formatted_payload)
    else:
        payload = format_string(str(payload_config), state)

    logger.debug(
        f"Publishing MQTT message to topic '{topic}' with payload '{payload}' "
        f"(qos={qos}, retain={retain})"
    )
    publish_mqtt_message_request.send(
        None, topic=topic, payload=payload, qos=qos, retain=retain
    )
