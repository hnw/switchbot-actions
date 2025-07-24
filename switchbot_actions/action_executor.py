import logging
import subprocess

import requests

from .evaluator import StateObject, format_string

logger = logging.getLogger(__name__)


def execute_action(action: dict, state: StateObject):
    """Executes the specified action (e.g., shell command, webhook)."""
    action_type = action.get("type")

    if action_type == "shell_command":
        command = format_string(action["command"], state)
        logger.debug(f"Executing shell command: {command}")
        subprocess.run(command, shell=True, check=False)

    elif action_type == "webhook":
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
        formatted_headers = {
            k: format_string(str(v), state) for k, v in headers.items()
        }

        logger.debug(
            f"Sending webhook: {method} {url} with payload {formatted_payload} "
            f"and headers {formatted_headers}"
        )
        try:
            if method == "POST":
                requests.post(
                    url, json=formatted_payload, headers=formatted_headers, timeout=10
                )
            elif method == "GET":
                requests.get(
                    url, params=formatted_payload, headers=formatted_headers, timeout=10
                )
        except requests.RequestException as e:
            logger.error(f"Webhook failed: {e}")

    else:
        logger.warning(f"Unknown trigger type: {action_type}")
