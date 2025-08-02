import json
import logging
import operator
import string
from typing import Any, Dict, TypeAlias, Union, overload

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


def _get_values_as_dict(state: StateObject) -> Dict[str, Any]:
    """Extracts all relevant key-value pairs from the state object into a dictionary."""
    if isinstance(state, SwitchBotAdvertisement):
        flat_data = state.data.get("data", {})
        for key, value in state.data.items():
            if key != "data":
                flat_data[key] = value
        if hasattr(state, "address"):
            flat_data["address"] = state.address
        if hasattr(state, "rssi"):
            flat_data["rssi"] = state.rssi
        return flat_data
    elif isinstance(state, aiomqtt.Message):
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
        return format_data
    return {}


def get_state_key(state: StateObject) -> str:
    """Returns a unique key from the state object."""
    if isinstance(state, SwitchBotAdvertisement):
        return state.address
    elif isinstance(state, aiomqtt.Message):
        return str(state.topic)
    raise TypeError(f"Unsupported state object type: {type(state)}")


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
        elif isinstance(new_value, str):
            expected_value = val_str
        else:
            expected_value = type(new_value)(val_str)
        return op(new_value, expected_value)
    except (ValueError, TypeError):
        return False


def check_conditions(if_config: AutomationIf, state: StateObject) -> bool | None:
    """Checks if the state object meets all specified conditions."""
    source = if_config.source
    if source.startswith("switchbot") and not isinstance(state, SwitchBotAdvertisement):
        return None
    if source.startswith("mqtt") and not isinstance(state, aiomqtt.Message):
        return None
    if not (source.startswith("switchbot") or source.startswith("mqtt")):
        return None

    if source.startswith("mqtt") and isinstance(state, aiomqtt.Message):
        if if_config.topic:
            if not aiomqtt.Topic(if_config.topic).matches(str(state.topic)):
                return None

    all_values = _get_values_as_dict(state)

    for key, condition in if_config.conditions.items():
        new_value = all_values.get(key)
        if new_value is None:
            return None  # Skip evaluation if the key doesn't exist in the state

        if not evaluate_condition(condition, new_value):
            return False

    return True


@overload
def format_object(template_data: str, state: StateObject) -> str: ...


@overload
def format_object(
    template_data: Dict[str, Any], state: StateObject
) -> Dict[str, Any]: ...


def format_object(
    template_data: Union[str, Dict[str, Any]], state: StateObject
) -> Union[str, Dict[str, Any]]:
    if isinstance(template_data, dict):
        return {k: format_string(str(v), state) for k, v in template_data.items()}
    else:
        return format_string(str(template_data), state)


def format_string(template_string: str, state: StateObject) -> str:
    """Replaces placeholders in a string with actual data."""
    all_values = _get_values_as_dict(state)
    formatter = MqttFormatter()  # Use MqttFormatter for dot notation support
    return formatter.format(template_string, **all_values)
