# switchbot_actions/dispatcher.py
import logging

from switchbot import SwitchBotAdvertisement

from . import triggers
from .handlers import RuleHandlerBase
from .mixins import MuteMixin

logger = logging.getLogger(__name__)


class EventDispatcher(RuleHandlerBase, MuteMixin):
    """
    Handles event-driven automation based on rules in the 'actions'
    section of the configuration by responding to state changes.
    """

    def __init__(self, actions_config: list):
        # Initialize RuleHandlerBase with the rules (renamed to actions)
        RuleHandlerBase.__init__(self, rules_config=actions_config)
        # Initialize MuteMixin
        MuteMixin.__init__(self)

    def on_conditions_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Triggers an action when its conditions transition from False to True.
        """
        action_name = rule.get("name", "Unnamed Action")
        device_address = new_data.address

        if self._is_muted(action_name, device_address):
            return

        logger.debug(
            f"Conditions met for action '{action_name}' on device "
            f"{device_address}. Triggering."
        )
        triggers.trigger_action(rule["trigger"], new_data)
        self._mute_action(action_name, device_address, rule.get("cooldown"))

    def on_conditions_no_longer_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Does nothing when conditions transition from True to False.
        """
        pass
