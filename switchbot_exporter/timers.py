# switchbot_exporter/timers.py
import logging
import asyncio
from switchbot import SwitchBotAdvertisement
from pytimeparse2 import parse
from .signals import advertisement_received
from .store import DeviceStateStore
from . import triggers
from .mixins import MuteMixin

logger = logging.getLogger(__name__)

class TimerHandler(MuteMixin):
    """
    Handles time-driven automation using an asyncio-native approach.
    """
    def __init__(self, timers_config: list, store: DeviceStateStore):
        super().__init__()
        self.timers = timers_config
        self._store = store
        self._active_timers = {}  # Stores {timer_key: asyncio.Task}
        advertisement_received.connect(self.handle_signal)
        logger.info(f"TimerHandler initialized with {len(self.timers)} timer(s).")

    def handle_signal(self, sender, **kwargs):
        """
        Receives device data and starts or cancels timer tasks.
        """
        new_data: SwitchBotAdvertisement = kwargs.get('new_data')
        if not new_data:
            return

        for timer_config in self.timers:
            timer_name = timer_config.get('name')
            device_address = new_data.address
            timer_key = (timer_name, device_address)

            if triggers.check_conditions(timer_config['conditions'], new_data, None):
                # Start timer if not already running
                if timer_key not in self._active_timers:
                    duration_str = timer_config.get('duration')
                    task = asyncio.create_task(self._run_timer(timer_config, device_address, duration_str))
                    self._active_timers[timer_key] = task
            else:
                # Cancel timer if it is running
                if timer_key in self._active_timers:
                    logger.info(f"Conditions no longer met for timer '{timer_name}' on device {device_address}. Cancelling.")
                    task = self._active_timers.pop(timer_key)
                    task.cancel()

    async def _run_timer(self, timer_config: dict, device_address: str, duration_str: str):
        """
        Waits for the duration, then triggers the action if not muted.
        """
        duration_sec = parse(duration_str)
        if duration_sec is None:
            return

        timer_name = timer_config.get('name')
        timer_key = (timer_name, device_address)
        try:
            await asyncio.sleep(duration_sec)

            if self._is_muted(timer_name, device_address):
                logger.info(f"Timer '{timer_name}' expired but is currently muted.")
                return

            device_data = self._store.get_state(device_address)
            if device_data:
                logger.info(f"Timer '{timer_name}' for device {device_address} expired. Triggering action.")
                triggers.trigger_action(timer_config['trigger'], device_data)
                self._mute_action(timer_name, device_address, timer_config.get('mute_for'))
        
        except asyncio.CancelledError:
            logger.info(f"Timer '{timer_name}' for device {device_address} was cancelled.")
        
        finally:
            self._active_timers.pop(timer_key, None)
