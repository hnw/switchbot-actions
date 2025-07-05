# switchbot_exporter/dispatcher.py
import logging
import subprocess
import requests
import operator
from .signals import advertisement_received
from switchbot import SwitchBotAdvertisement

logger = logging.getLogger(__name__)

# Operator mapping for condition checks
OPERATORS = {
    '==': operator.eq,
    '!=': operator.ne,
    '>': operator.gt,
    '<': operator.lt,
    '>=': operator.ge,
    '<=': operator.le,
}

class EventDispatcher:
    """
    Listens for device advertisements and triggers actions based on
    user-defined rules in the configuration.
    """
    def __init__(self, actions_config: list):
        self.actions = actions_config
        advertisement_received.connect(self.handle_advertisement)
        logger.info(f"EventDispatcher initialized with {len(self.actions)} action(s).")

    def handle_advertisement(self, sender, **kwargs):
        """Receives device data and checks if any action should be triggered."""
        device_data: SwitchBotAdvertisement = kwargs.get('device_data')
        if not device_data:
            return

        for action in self.actions:
            try:
                if self._conditions_met(action['event_conditions'], device_data):
                    logger.info(f"Conditions met for action '{action['name']}'. Triggering.")
                    self._trigger_action(action['trigger'], device_data)
            except Exception as e:
                logger.error(f"Error processing action '{action.get('name', 'Unnamed')}': {e}", exc_info=True)

    def _conditions_met(self, conditions: dict, device_data: SwitchBotAdvertisement) -> bool:
        """Checks if the device data meets all specified conditions."""
        # Check top-level attributes (e.g., modelName, address)
        if 'address' in conditions and device_data.address != conditions['address']:
            return False
        if 'modelName' in conditions and device_data.data.get('modelName') != conditions['modelName']:
            return False

        # Check nested data attributes
        if 'data' in conditions:
            for key, expected_value in conditions['data'].items():
                actual_value = device_data.data.get('data', {}).get(key)
                if actual_value is None:
                    return False  # The key we want to check doesn't exist in the event

                if isinstance(expected_value, str) and expected_value.split(' ')[0] in OPERATORS:
                    # Handle operator-based comparison (e.g., "> 25.0")
                    parts = expected_value.split(' ', 1)
                    op_str = parts[0]
                    val_str = parts[1]
                    
                    op = OPERATORS[op_str]
                    try:
                        # Try to cast the expected value to the same type as the actual value
                        if not op(actual_value, type(actual_value)(val_str)):
                            return False
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not compare values for condition '{key} {op_str} {val_str}' (actual: {actual_value}, expected: {expected_value}). This might indicate an invalid value in your config.yaml. Error: {e}")
                        return False # Could not compare values
                else:
                    # Handle direct equality comparison
                    if actual_value != expected_value:
                        return False
        
        return True

    def _trigger_action(self, trigger: dict, device_data: SwitchBotAdvertisement):
        """Executes the specified action (e.g., shell command, webhook)."""
        trigger_type = trigger.get('type')
        
        if trigger_type == 'shell_command':
            command = self._format_string(trigger['command'], device_data)
            logger.info(f"Executing shell command: {command}")
            subprocess.run(command, shell=True, check=False)

        elif trigger_type == 'webhook':
            url = self._format_string(trigger['url'], device_data)
            method = trigger.get('method', 'POST').upper()
            payload = trigger.get('payload', {})

            # Format payload values if it's a dictionary
            if isinstance(payload, dict):
                formatted_payload = {
                    k: self._format_string(str(v), device_data) for k, v in payload.items()
                }
            else:
                formatted_payload = self._format_string(str(payload), device_data)

            logger.info(f"Sending webhook: {method} {url} with payload {formatted_payload}")
            try:
                if method == 'POST':
                    requests.post(url, json=formatted_payload, timeout=10)
                elif method == 'GET':
                    requests.get(url, params=formatted_payload, timeout=10)
            except requests.RequestException as e:
                logger.error(f"Webhook failed: {e}. Please check the URL in your config.yaml and your network connection.")

        else:
            logger.warning(f"Unknown trigger type: {trigger_type}")

    def _format_string(self, template_string: str, device_data: SwitchBotAdvertisement) -> str:
        """Replaces placeholders like {temperature} in a string with actual data."""
        # Flatten the data for easy replacement
        flat_data = {**device_data.data.get('data', {}), 'address': device_data.address, 'modelName': device_data.data.get('modelName')}
        return template_string.format(**flat_data)
