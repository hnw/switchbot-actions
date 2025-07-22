# switchbot_actions/handlers.py
import logging
from abc import ABC, abstractmethod

from switchbot import SwitchBotAdvertisement

from . import triggers
from .signals import advertisement_received

logger = logging.getLogger(__name__)


class AutomationHandlerBase(ABC):
    """
    Abstract base class for handling rules based on device state changes.

    This class provides the core logic for detecting state transitions
    (e.g., from False to True) based on a set of conditions. Subclasses
    must implement the specific actions to be taken when these transitions
    occur.
    """

    def __init__(self, configs: list):
        """
        Initializes the handler.

        Args:
            configs: A list of rule configurations. Each rule must
                     have a 'name' and 'conditions'.
        """
        self._configs = configs
        self._last_condition_results = {}  # Stores {key: bool}
        advertisement_received.connect(self.handle_signal)
        logger.info(
            f"{self.__class__.__name__} initialized with {len(self._configs)} rule(s)."
        )

    def handle_signal(self, sender, **kwargs):
        """
        Receives device data, checks conditions, and triggers actions
        on state changes.
        """
        new_data_untyped = kwargs.get("new_data")
        if not new_data_untyped:
            return

        new_data: SwitchBotAdvertisement = new_data_untyped

        for config in self._configs:
            config_name = config.get("name", "Unnamed Automation")
            device_address = new_data.address
            key = (config_name, device_address)

            try:
                current_result = self._check_conditions_from_config(config, new_data)
                last_result = self._last_condition_results.get(key, False)

                # State changed: False -> True
                if current_result and not last_result:
                    self.on_conditions_met(config, new_data)

                # State changed: True -> False
                elif not current_result and last_result:
                    self.on_conditions_no_longer_met(config, new_data)

                self._last_condition_results[key] = current_result

            except Exception as e:
                logger.error(
                    f"Error processing config '{config_name}' in "
                    f"{self.__class__.__name__}: {e}",
                    exc_info=True,
                )

    @abstractmethod
    def on_conditions_met(self, config: dict, new_data: SwitchBotAdvertisement):
        """
        Callback executed when conditions transition from False to True.
        """
        pass

    def _check_conditions_from_config(
        self, config: dict, new_data: SwitchBotAdvertisement
    ) -> bool:
        """
        Helper method to check conditions from a given config and new_data.
        """
        device_cond = config.get("if", {}).get("device", {})
        state_cond = config.get("if", {}).get("state", {})
        return triggers.check_conditions(device_cond, state_cond, new_data)

    @abstractmethod
    def on_conditions_no_longer_met(
        self, config: dict, new_data: SwitchBotAdvertisement
    ):
        """
        Callback executed when conditions transition from True to False.
        """
        pass
