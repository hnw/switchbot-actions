# switchbot_actions/scanner.py
import asyncio
import logging

from switchbot import (
    GetSwitchbotDevices,
    SwitchBotAdvertisement,
)

from .signals import switchbot_advertisement_received
from .store import StateStore

logger = logging.getLogger(__name__)


class SwitchbotClient:
    """
    Continuously scans for SwitchBot BLE advertisements and serves as the
    central publisher of device events.
    """

    def __init__(
        self,
        scanner: GetSwitchbotDevices,
        store: StateStore,
        cycle: int = 10,
        duration: int = 3,
    ):
        self._scanner = scanner
        self._store = store
        self._cycle = cycle
        self._duration = duration
        self._running = False

    async def start_scan(self):
        """Starts the continuous scanning loop for SwitchBot devices."""
        self._running = True
        while self._running:
            try:
                logger.debug(f"Starting BLE scan for {self._duration} seconds...")
                devices = await self._scanner.discover(scan_timeout=self._duration)

                for address, device in devices.items():
                    self._process_advertisement(device)

                # Wait for the remainder of the cycle
                wait_time = self._cycle - self._duration
                if self._running and wait_time > 0:
                    logger.debug(f"Scan finished, waiting for {wait_time} seconds.")
                    await asyncio.sleep(wait_time)

            except Exception as e:
                message, is_known_error = self._format_ble_error_message(e)
                if is_known_error:
                    logger.error(message)
                else:
                    logger.error(message, exc_info=True)
                # In case of error, wait for the full cycle time to avoid spamming
                if self._running:
                    await asyncio.sleep(self._cycle)

    def stop_scan(self):
        """Stops the scanning loop."""
        self._running = False

    def _format_ble_error_message(self, exception: Exception) -> tuple[str, bool]:
        """Generates a user-friendly error message for BLE scan exceptions."""
        err_str = str(exception).lower()
        message = f"Error during BLE scan: {exception}. "
        is_known_error = False

        if "bluetooth device is turned off" in err_str:
            message += "Please ensure your Bluetooth adapter is turned on."
            is_known_error = True
        elif "ble is not authorized" in err_str:
            message += "Please check your OS's privacy settings for Bluetooth."
            is_known_error = True
        elif (
            "permission denied" in err_str
            or "not permitted" in err_str
            or "access denied" in err_str
        ):
            message += (
                "Check if the program has Bluetooth permissions "
                "(e.g., run with sudo or set udev rules)."
            )
            is_known_error = True
        elif "no such device" in err_str:
            message += (
                "Bluetooth device not found. Ensure hardware is working correctly."
            )
            is_known_error = True
        else:
            message += (
                "This might be due to adapter issues, permissions, "
                "or other environmental factors."
            )
            is_known_error = False
        return message, is_known_error

    def _process_advertisement(self, new_state: SwitchBotAdvertisement):
        """
        Processes a new advertisement and
        emits a switchbot_advertisement_received signal.
        """
        if not new_state.data:
            return

        logger.debug(
            f"Received advertisement from {new_state.address}: {new_state.data}"
        )
        switchbot_advertisement_received.send(self, new_state=new_state)
