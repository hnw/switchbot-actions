# switchbot_actions/store.py
import logging
from threading import Lock

from switchbot import SwitchBotAdvertisement

from . import evaluator
from .signals import switchbot_advertisement_received

logger = logging.getLogger(__name__)


class StateStore:
    """
    An in-memory, thread-safe store for the latest state of each entity.
    """

    def __init__(self):
        self._states: dict[str, SwitchBotAdvertisement] = {}
        self._lock = Lock()
        # Connect to the signal to receive updates
        switchbot_advertisement_received.connect(self.handle_state_change)

    def handle_state_change(self, sender, **kwargs):
        """Receives state object from the signal and updates the store."""
        new_state = kwargs.get("new_state")
        if not new_state:
            return

        state_obj = evaluator.create_state_object(new_state)
        key = state_obj.id
        with self._lock:
            self._states[key] = new_state
        logger.debug(f"State updated for key {key}")

    def get_state(self, key: str) -> SwitchBotAdvertisement | None:
        """
        Retrieves the latest state for a specific key.
        Returns None if no state is associated with the key.
        """
        with self._lock:
            return self._states.get(key)

    def get_all_states(self) -> dict[str, SwitchBotAdvertisement]:
        """
        Retrieves a copy of the states of all entities.
        """
        with self._lock:
            return self._states.copy()
