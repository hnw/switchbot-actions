# switchbot_actions/evaluator.py
import logging
import operator
from typing import TypeAlias

from switchbot import SwitchBotAdvertisement

# For now, StateObject is just a SwitchBotAdvertisement.
# This will be expanded to a Union type in the future.
StateObject: TypeAlias = SwitchBotAdvertisement

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
    """Returns a unique key from the state object, e.g., a MAC address."""
    return state.address


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


def check_conditions(if_config: dict, state: StateObject) -> bool | None:
    """Checks if the state object meets all specified conditions."""
    device_cond = if_config.get("device", {})
    state_cond = if_config.get("state", {})

    # Check device conditions
    for key, expected_value in device_cond.items():
        if key == "address":
            actual_value = state.address
        else:
            actual_value = state.data.get(key)
        if actual_value != expected_value:
            return False

    # Check state conditions
    for key, condition in state_cond.items():
        new_value = None
        if key == "rssi":
            # Special handling for RSSI, which is not in the 'data' dict
            new_value = getattr(state, "rssi", None)
        else:
            # For all other keys, look inside the 'data' dict
            if "data" in state.data and key in state.data["data"]:
                new_value = state.data["data"][key]
            else:
                # If the key is not in the advertisement, we cannot evaluate
                # the condition. This is not a failure, but we cannot confirm
                # the condition is met.
                return None

        if not evaluate_condition(condition, new_value):
            return False

    return True


def format_string(template_string: str, state: StateObject) -> str:
    """Replaces placeholders like {temperature} in a string with actual data."""
    flat_data = {
        **state.data.get("data", {}),
        "address": state.address,
        "modelName": state.data.get("modelName"),
        "rssi": getattr(state, "rssi", None),
    }
    return template_string.format(**flat_data)
