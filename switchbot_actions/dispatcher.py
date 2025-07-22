# switchbot_actions/dispatcher.py
import logging

from switchbot import SwitchBotAdvertisement

from . import triggers
from .handlers import AutomationHandlerBase
from .mixins import MuteMixin

logger = logging.getLogger(__name__)


class EventDispatcher(AutomationHandlerBase, MuteMixin):
    """
    Handles event-driven automation based on rules where `if.source` is 'switchbot'.
    """

    def __init__(self, configs: list):
        AutomationHandlerBase.__init__(self, configs)
        MuteMixin.__init__(self)

    def on_conditions_met(self, config: dict, new_data: SwitchBotAdvertisement):
        """
        Triggers an action when its conditions transition from False to True.
        """
        action_name = config.get("name", "Unnamed Automation")
        device_address = new_data.address

        if self._is_muted(action_name, device_address):
            return

        logger.debug(
            f"Conditions met for action '{action_name}' on device "
            f"{device_address}. Triggering."
        )
        triggers.trigger_action(config.get("then", {}), new_data)
        self._mute_action(action_name, device_address, config.get("cooldown"))

    def on_conditions_no_longer_met(
        self, config: dict, new_data: SwitchBotAdvertisement
    ):
        """
        Does nothing when conditions transition from True to False.
        """
        pass
