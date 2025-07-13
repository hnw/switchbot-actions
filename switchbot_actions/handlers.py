# switchbot_actions/handlers.py
import logging
from abc import ABC, abstractmethod

from switchbot import SwitchBotAdvertisement

from . import triggers
from .signals import advertisement_received

logger = logging.getLogger(__name__)


class RuleHandlerBase(ABC):
    """
    Abstract base class for handling rules based on device state changes.

    This class provides the core logic for detecting state transitions
    (e.g., from False to True) based on a set of conditions. Subclasses
    must implement the specific actions to be taken when these transitions
    occur.
    """

    def __init__(self, rules_config: list):
        """
        Initializes the handler.

        Args:
            rules_config: A list of rule configurations. Each rule must
                          have a 'name' and 'conditions'.
        """
        self._rules = rules_config
        self._last_condition_results = {}  # Stores {key: bool}
        advertisement_received.connect(self.handle_signal)
        logger.info(
            f"{self.__class__.__name__} initialized with {len(self._rules)} rule(s)."
        )

    def handle_signal(self, sender, **kwargs):
        """
        Receives device data, checks conditions, and triggers actions
        on state changes.
        """
        new_data: SwitchBotAdvertisement = kwargs.get("new_data")
        if not new_data:
            return

        for rule in self._rules:
            rule_name = rule.get("name", "Unnamed Rule")
            device_address = new_data.address
            key = (rule_name, device_address)

            try:
                current_result = triggers.check_conditions(rule["conditions"], new_data)
                last_result = self._last_condition_results.get(key, False)

                # State changed: False -> True
                if current_result and not last_result:
                    self.on_conditions_met(rule, new_data)

                # State changed: True -> False
                elif not current_result and last_result:
                    self.on_conditions_no_longer_met(rule, new_data)

                self._last_condition_results[key] = current_result

            except Exception as e:
                logger.error(
                    f"Error processing rule '{rule_name}' in "
                    f"{self.__class__.__name__}: {e}",
                    exc_info=True,
                )

    @abstractmethod
    def on_conditions_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Callback executed when conditions transition from False to True.
        """
        pass

    @abstractmethod
    def on_conditions_no_longer_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Callback executed when conditions transition from True to False.
        """
        pass
