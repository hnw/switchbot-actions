# switchbot_actions/timers.py
import asyncio
import logging

from pytimeparse2 import parse
from switchbot import SwitchBotAdvertisement

from . import triggers
from .handlers import AutomationHandlerBase
from .mixins import MuteMixin
from .store import DeviceStateStore

logger = logging.getLogger(__name__)


class TimerHandler(AutomationHandlerBase, MuteMixin):
    """
    Handles time-driven automation by starting and stopping timers
    based on state changes.
    """

    def __init__(self, configs: list, store: DeviceStateStore):
        AutomationHandlerBase.__init__(self, configs)
        MuteMixin.__init__(self)
        self._store = store
        self._active_timers = {}  # Stores {key: asyncio.Task}

    def on_conditions_met(self, config: dict, new_data: SwitchBotAdvertisement):
        """
        Starts a timer when its conditions transition from False to True.
        """
        timer_name = config.get("name", "Unnamed Timer")
        device_address = new_data.address
        key = (timer_name, device_address)

        if key not in self._active_timers:
            logger.debug(
                f"Conditions met for timer '{timer_name}' on device "
                f"{device_address}. Starting timer."
            )
            duration_str = config.get("if", {}).get("duration")
            task = asyncio.create_task(
                self._run_timer(config, device_address, duration_str)
            )
            self._active_timers[key] = task

    def on_conditions_no_longer_met(
        self, config: dict, new_data: SwitchBotAdvertisement
    ):
        """
        Cancels an active timer when its conditions transition from
        True to False.
        """
        timer_name = config.get("name", "Unnamed Timer")
        device_address = new_data.address
        key = (timer_name, device_address)

        if key in self._active_timers:
            logger.debug(
                f"Conditions no longer met for timer '{timer_name}' on "
                f"device {device_address}. Cancelling."
            )
            task = self._active_timers.pop(key)
            task.cancel()

    async def _run_timer(
        self, config: dict, device_address: str, duration_str: str | None
    ):
        """
        Waits for the duration, then triggers the action if not muted.
        """
        if duration_str is None:
            logger.error(f"Timer '{config.get('name')}' has no duration set.")
            return

        duration = parse(duration_str)
        if duration is None:
            logger.error(
                f"Invalid duration '{duration_str}' for timer '{config.get('name')}'."
            )
            return

        if isinstance(duration, (int, float)):
            duration_sec = float(duration)
        else:
            duration_sec = duration.total_seconds()

        timer_name = config.get("name", "Unnamed Automation")
        timer_key = (timer_name, device_address)
        try:
            await asyncio.sleep(float(duration_sec))

            current_data = self._store.get_state(device_address)
            if not current_data:
                logger.debug(
                    f"Timer '{timer_name}' for device {device_address} expired, but "
                    f"device state is no longer available. Not triggering."
                )
                return

            conditions_met = self._check_conditions_from_config(config, current_data)
            if not conditions_met:
                logger.debug(
                    f"Timer '{timer_name}' for device {device_address} expired, but "
                    f"conditions are no longer met. Not triggering."
                )
                return

            if self._is_muted(timer_name, device_address):
                logger.debug(f"Timer '{timer_name}' expired but is currently muted.")
                return

            logger.debug(
                f"Timer '{timer_name}' for device {device_address} expired. "
                "Triggering action."
            )
            triggers.trigger_action(config.get("then", {}), current_data)
            self._mute_action(timer_name, device_address, config.get("cooldown"))

        except asyncio.CancelledError:
            logger.debug(
                f"Timer '{timer_name}' for device {device_address} was cancelled."
            )

        finally:
            self._active_timers.pop(timer_key, None)
