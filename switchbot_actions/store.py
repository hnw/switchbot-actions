# switchbot_actions/store.py
import logging
from threading import Lock

from . import evaluator
from .evaluator import StateObject
from .signals import state_changed

logger = logging.getLogger(__name__)


class StateStorage:
    """
    An in-memory, thread-safe store for the latest state of each entity.
    """

    def __init__(self):
        self._states: dict[str, StateObject] = {}
        self._lock = Lock()
        # Connect to the signal to receive updates
        state_changed.connect(self.handle_state_change)

    def handle_state_change(self, sender, **kwargs):
        """Receives state object from the signal and updates the store."""
        new_state = kwargs.get("new_state")
        if not new_state:
            return

        key = evaluator.get_state_key(new_state)
        with self._lock:
            self._states[key] = new_state
        logger.debug(f"State updated for key {key}")

    def get_state(self, key: str) -> StateObject | None:
        """
        Retrieves the latest state for a specific key.
        Returns None if no state is associated with the key.
        """
        with self._lock:
            return self._states.get(key)

    def get_all_states(self) -> dict[str, StateObject]:
        """
        Retrieves a copy of the states of all entities.
        """
        with self._lock:
            return self._states.copy()
