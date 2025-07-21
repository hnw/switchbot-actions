# switchbot_actions/mixins.py
import logging
import time

from pytimeparse2 import parse

logger = logging.getLogger(__name__)


class MuteMixin:
    """A mixin to provide timed, per-device muting functionality."""

    def __init__(self):
        # The key is a tuple: (name, device_address)
        self._last_triggered: dict[tuple[str, str], float] = {}

    def _is_muted(self, name: str, device_address: str) -> bool:
        """Checks if a named action for a specific device is currently muted."""
        mute_key = (name, device_address)
        mute_until = self._last_triggered.get(mute_key)
        if mute_until is None:
            return False
        return time.time() < mute_until

    def _mute_action(self, name: str, device_address: str, cooldown: str | None):
        """Starts the mute period for a named action on a specific device."""
        if not cooldown:
            return

        duration = parse(cooldown)
        if duration is not None:
            if isinstance(duration, (int, float)):
                duration_seconds = float(duration)
            else:
                duration_seconds = duration.total_seconds()
            mute_key = (name, device_address)
            self._last_triggered[mute_key] = time.time() + duration_seconds
            logger.debug(
                f"Action '{name}' for device {device_address} muted "
                f"for {duration_seconds}s."
            )
