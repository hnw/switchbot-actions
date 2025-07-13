# switchbot_actions/timers.py
import asyncio
import logging

from pytimeparse2 import parse
from switchbot import SwitchBotAdvertisement

from . import triggers
from .handlers import RuleHandlerBase
from .mixins import MuteMixin
from .store import DeviceStateStore

logger = logging.getLogger(__name__)


class TimerHandler(RuleHandlerBase, MuteMixin):
    """
    Handles time-driven automation by starting and stopping timers
    based on state changes.
    """

    def __init__(self, timers_config: list, store: DeviceStateStore):
        RuleHandlerBase.__init__(self, rules_config=timers_config)
        MuteMixin.__init__(self)
        self._store = store
        self._active_timers = {}  # Stores {key: asyncio.Task}

    def on_conditions_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Starts a timer when its conditions transition from False to True.
        """
        timer_name = rule.get("name")
        device_address = new_data.address
        key = (timer_name, device_address)

        if key not in self._active_timers:
            logger.debug(
                f"Conditions met for timer '{timer_name}' on device "
                f"{device_address}. Starting timer."
            )
            duration_str = rule.get("duration")
            task = asyncio.create_task(
                self._run_timer(rule, device_address, duration_str)
            )
            self._active_timers[key] = task

    def on_conditions_no_longer_met(self, rule: dict, new_data: SwitchBotAdvertisement):
        """
        Cancels an active timer when its conditions transition from
        True to False.
        """
        timer_name = rule.get("name")
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
        self, timer_config: dict, device_address: str, duration_str: str
    ):
        """
        Waits for the duration, then triggers the action if not muted.
        """
        if duration_str is None:
            logger.error(f"Timer '{timer_config.get('name')}' has no duration set.")
            return

        duration_sec = parse(duration_str)
        if duration_sec is None:
            logger.error(
                f"Invalid duration '{duration_str}' for timer "
                f"'{timer_config.get('name')}'."
            )
            return

        timer_name = timer_config.get("name")
        timer_key = (timer_name, device_address)
        try:
            await asyncio.sleep(duration_sec)

            current_data = self._store.get_state(device_address)
            if not current_data or not triggers.check_conditions(
                timer_config["conditions"], current_data
            ):
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
            triggers.trigger_action(timer_config["trigger"], current_data)
            self._mute_action(timer_name, device_address, timer_config.get("cooldown"))

        except asyncio.CancelledError:
            logger.debug(
                f"Timer '{timer_name}' for device {device_address} was cancelled."
            )

        finally:
            self._active_timers.pop(timer_key, None)
