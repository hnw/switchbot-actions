import json
import logging
import operator
import string
from typing import Any, TypeAlias, Union

import aiomqtt
from switchbot import SwitchBotAdvertisement

from .config import AutomationIf

StateObject: TypeAlias = Union[SwitchBotAdvertisement, aiomqtt.Message]

logger = logging.getLogger(__name__)

OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def get_state_key(state: StateObject) -> str:
    """Returns a unique key from the state object."""
    if isinstance(state, SwitchBotAdvertisement):
        return state.address
    elif isinstance(state, aiomqtt.Message):
        return str(state.topic)
    raise TypeError(f"Unsupported state object type: {type(state)}")


def get_value_from_state(state: StateObject, key: str) -> Any:
    """Extracts a value from the state object based on the key."""
    if isinstance(state, SwitchBotAdvertisement):
        if key == "rssi":
            return getattr(state, "rssi", None)
        return state.data.get("data", {}).get(key)
    elif isinstance(state, aiomqtt.Message):
        if isinstance(state.payload, bytes):
            payload_decoded = state.payload.decode()
        else:
            payload_decoded = str(state.payload)

        try:
            payload_json = json.loads(payload_decoded)
        except json.JSONDecodeError:
            payload_json = None

        if key == "payload":
            return payload_decoded
        if isinstance(payload_json, dict):
            return payload_json.get(key)
    return None


def evaluate_condition(condition: str, new_value: Any) -> bool:
    """Evaluates a single state condition."""
    parts = str(condition).split(" ", 1)
    op_str = "=="
    val_str = str(condition)

    if len(parts) == 2 and parts[0] in OPERATORS:
        op_str = parts[0]
        val_str = parts[1]

    op = OPERATORS.get(op_str, operator.eq)

    try:
        if new_value is None:
            return False
        if isinstance(new_value, bool):
            expected_value = val_str.lower() in ("true", "1", "t", "y", "yes")
        else:
            expected_value = type(new_value)(val_str)
        return op(new_value, expected_value)
    except (ValueError, TypeError):
        return False


def check_conditions(if_config: AutomationIf, state: StateObject) -> bool | None:
    """Checks if the state object meets all specified conditions."""
    source = if_config.source
    if source in ["switchbot", "switchbot_timer"] and isinstance(
        state, SwitchBotAdvertisement
    ):
        return _check_switchbot_conditions(if_config, state)
    elif source in ["mqtt", "mqtt_timer"] and isinstance(state, aiomqtt.Message):
        return _check_mqtt_conditions(if_config, state)
    return None  # Not applicable


def _check_switchbot_conditions(
    if_config: AutomationIf, state: SwitchBotAdvertisement
) -> bool | None:
    device_cond = if_config.device
    state_cond = if_config.state

    for key, expected_value in device_cond.items():
        if key == "address":
            actual_value = state.address
        else:
            actual_value = state.data.get(key)
        if actual_value != expected_value:
            return False

    for key, condition in state_cond.items():
        new_value = get_value_from_state(state, key)
        if new_value is None:
            return None

        if not evaluate_condition(condition, new_value):
            return False

    return True


def _check_mqtt_conditions(
    if_config: AutomationIf, state: aiomqtt.Message
) -> bool | None:
    mqtt_topic = if_config.topic
    if not mqtt_topic:
        return None

    if not aiomqtt.Topic(mqtt_topic).matches(state.topic):
        return None

    state_cond = if_config.state
    for key, condition in state_cond.items():
        new_value = get_value_from_state(state, key)
        if new_value is None:
            return None

        if not evaluate_condition(condition, new_value):
            return False

    return True


def format_string(template_string: str, state: StateObject) -> str:
    """Replaces placeholders in a string with actual data."""
    if isinstance(state, SwitchBotAdvertisement):
        return _format_switchbot_string(template_string, state)
    elif isinstance(state, aiomqtt.Message):
        return _format_mqtt_string(template_string, state)
    return template_string


def _format_switchbot_string(
    template_string: str, state: SwitchBotAdvertisement
) -> str:
    flat_data = {
        **state.data.get("data", {}),
        "address": state.address,
        "modelName": state.data.get("modelName"),
        "rssi": getattr(state, "rssi", None),
    }
    return str(template_string).format(**flat_data)


class MqttFormatter(string.Formatter):
    def get_field(self, field_name, args, kwargs):
        # Handle dot notation for nested access
        obj = kwargs
        for part in field_name.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return (
                    None,
                    field_name,
                )  # Return None if not found, and original field_name
        return obj, field_name


def _format_mqtt_string(template_string: str, state: aiomqtt.Message) -> str:
    if isinstance(state.payload, bytes):
        payload_decoded = state.payload.decode()
    else:
        payload_decoded = str(state.payload)

    format_data = {"topic": str(state.topic), "payload": payload_decoded}
    try:
        payload_json = json.loads(payload_decoded)
        if isinstance(payload_json, dict):
            format_data.update(payload_json)
    except json.JSONDecodeError:
        pass

    formatter = MqttFormatter()
    return formatter.format(template_string, **format_data)
