# switchbot_exporter/dispatcher.py
import logging
from .signals import advertisement_received
from switchbot import SwitchBotAdvertisement
from . import triggers
from .mixins import MuteMixin

logger = logging.getLogger(__name__)

class EventDispatcher(MuteMixin):
    """
    Handles event-driven automation based on rules in the 'actions'
    section of the configuration.
    """
    def __init__(self, actions_config: list):
        super().__init__()
        self.actions = actions_config
        advertisement_received.connect(self.handle_signal)
        logger.info(f"EventDispatcher initialized with {len(self.actions)} action(s).")

    def handle_signal(self, sender, **kwargs):
        """
        Receives device data and checks if any action
        should be triggered.
        """
        new_data: SwitchBotAdvertisement = kwargs.get('new_data')
        old_data: SwitchBotAdvertisement = kwargs.get('old_data')

        if not new_data:
            return

        for action in self.actions:
            action_name = action.get('name', 'Unnamed Action')
            try:
                if self._is_muted(action_name, new_data.address):
                    continue

                if triggers.check_conditions(action['conditions'], new_data, old_data):
                    logger.info(f"Conditions met for action '{action_name}'. Triggering.")
                    triggers.trigger_action(action['trigger'], new_data)
                    self._mute_action(action_name, new_data.address, action.get('mute_for'))

            except Exception as e:
                logger.error(f"Error processing action '{action_name}': {e}", exc_info=True)