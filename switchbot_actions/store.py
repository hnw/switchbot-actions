# switchbot_actions/store.py
import logging
from threading import Lock

from switchbot import SwitchBotAdvertisement

from .signals import advertisement_received

logger = logging.getLogger(__name__)


class DeviceStateStore:
    """
    An in-memory, thread-safe store for the latest state of each SwitchBot device.
    """

    def __init__(self):
        self._states = {}
        self._lock = Lock()
        # Connect to the signal to receive updates
        advertisement_received.connect(self.handle_advertisement)

    def handle_advertisement(self, sender, **kwargs):
        """Receives device data from the signal and updates the store."""
        new_data: SwitchBotAdvertisement = kwargs.get("new_data")
        if not new_data or not hasattr(new_data, "address"):
            return

        address = new_data.address
        with self._lock:
            self._states[address] = new_data
        logger.debug(f"State updated for device {address}")

    def get_state(self, address: str) -> SwitchBotAdvertisement | None:
        """
        Retrieves the latest state for a specific device by its MAC address.
        Returns None if the device has not been seen.
        """
        with self._lock:
            return self._states.get(address)

    def get_all_states(self) -> dict[str, SwitchBotAdvertisement]:
        """
        Retrieves a copy of the states of all seen devices.
        """
        with self._lock:
            return self._states.copy()
