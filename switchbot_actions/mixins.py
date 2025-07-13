# switchbot_actions/mixins.py
import logging
import time
from typing import Optional

from pytimeparse2 import parse

logger = logging.getLogger(__name__)


class MuteMixin:
    """A mixin to provide timed, per-device muting functionality."""

    def __init__(self):
        # The key is a tuple: (name, device_address)
        self._last_triggered = {}

    def _is_muted(self, name: str, device_address: str) -> bool:
        """Checks if a named action for a specific device is currently muted."""
        mute_key = (name, device_address)
        mute_until = self._last_triggered.get(mute_key)
        if mute_until is None:
            return False
        return time.time() < mute_until

    def _mute_action(self, name: str, device_address: str, cooldown: Optional[str]):
        """Starts the mute period for a named action on a specific device."""
        if not cooldown:
            return

        duration_seconds = parse(cooldown)
        if duration_seconds is not None and duration_seconds > 0:
            mute_key = (name, device_address)
            self._last_triggered[mute_key] = time.time() + duration_seconds
            logger.debug(
                f"Action '{name}' for device {device_address} muted "
                f"for {duration_seconds}s."
            )
