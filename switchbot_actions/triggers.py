# switchbot_actions/triggers.py
import logging
import operator
import subprocess

import requests
from switchbot import SwitchBotAdvertisement

logger = logging.getLogger(__name__)

OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def evaluate_condition(condition: str, new_value) -> bool:
    """Evaluates a single state condition."""
    # Standard comparison
    parts = str(condition).split(" ", 1)
    op_str = "=="
    val_str = str(condition)

    if len(parts) == 2 and parts[0] in OPERATORS:
        op_str = parts[0]
        val_str = parts[1]

    op = OPERATORS.get(op_str, operator.eq)

    try:
        # Cast the expected value to the same type as the actual value
        if new_value is None:
            return False
        if isinstance(new_value, bool):
            expected_value = val_str.lower() in ("true", "1", "t", "y", "yes")
        else:
            expected_value = type(new_value)(val_str)
        return op(new_value, expected_value)
    except (ValueError, TypeError):
        return False  # Could not compare


def check_conditions(conditions: dict, new_data: SwitchBotAdvertisement) -> bool:
    """Checks if the device data meets all specified conditions."""
    device_conditions = conditions.get("device", {})
    state_conditions = conditions.get("state", {})

    # Check device conditions
    for key, expected_value in device_conditions.items():
        if key == "address":
            actual_value = new_data.address
        else:
            actual_value = new_data.data.get(key)
        if actual_value != expected_value:
            return False

    # Check state conditions
    for key, condition in state_conditions.items():
        if key == "rssi":
            # Special handling for RSSI, which is not in the 'data' dict
            new_value = getattr(new_data, "rssi", None)
        else:
            # For all other keys, look inside the 'data' dict
            new_value = new_data.data.get("data", {}).get(key)

        if not evaluate_condition(condition, new_value):
            return False

    return True


def format_string(template_string: str, device_data: SwitchBotAdvertisement) -> str:
    """Replaces placeholders like {temperature} in a string with actual data."""
    flat_data = {
        **device_data.data.get("data", {}),
        "address": device_data.address,
        "modelName": device_data.data.get("modelName"),
        "rssi": getattr(device_data, "rssi", None),
    }
    return template_string.format(**flat_data)


def trigger_action(trigger: dict, device_data: SwitchBotAdvertisement):
    """Executes the specified action (e.g., shell command, webhook)."""
    trigger_type = trigger.get("type")

    if trigger_type == "shell_command":
        command = format_string(trigger["command"], device_data)
        logger.debug(f"Executing shell command: {command}")
        subprocess.run(command, shell=True, check=False)

    elif trigger_type == "webhook":
        url = format_string(trigger["url"], device_data)
        method = trigger.get("method", "POST").upper()
        payload = trigger.get("payload", {})
        headers = trigger.get("headers", {})

        # Format payload
        if isinstance(payload, dict):
            formatted_payload = {
                k: format_string(str(v), device_data) for k, v in payload.items()
            }
        else:
            formatted_payload = format_string(str(payload), device_data)

        # Format headers
        formatted_headers = {
            k: format_string(str(v), device_data) for k, v in headers.items()
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
        logger.warning(f"Unknown trigger type: {trigger_type}")
