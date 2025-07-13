# switchbot_actions/scanner.py
import asyncio
import logging

from switchbot import (
    GetSwitchbotDevices,
    SwitchBotAdvertisement,
)

from .signals import advertisement_received
from .store import DeviceStateStore

logger = logging.getLogger(__name__)


class DeviceScanner:
    """
    Continuously scans for SwitchBot BLE advertisements and serves as the
    central publisher of device events.
    """

    def __init__(
        self,
        scanner: GetSwitchbotDevices,
        store: DeviceStateStore,
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
                error_message = f"Error during BLE scan: {e}. "
                err_str = str(e).lower()
                if "bluetooth device is turned off" in err_str:
                    error_message += (
                        "Please ensure your Bluetooth adapter is turned on."
                    )
                elif "ble is not authorized" in err_str:
                    error_message += (
                        "Please check your OS's privacy settings for Bluetooth."
                    )
                elif (
                    "permission denied" in err_str
                    or "not permitted" in err_str
                    or "access denied" in err_str
                ):
                    error_message += (
                        "Check if the program has Bluetooth permissions "
                        "(e.g., run with sudo or set udev rules)."
                    )
                elif "no such device" in err_str:
                    error_message += (
                        "Bluetooth device not found. "
                        "Ensure hardware is working correctly."
                    )
                else:
                    error_message += (
                        "This might be due to adapter issues, permissions, "
                        "or other environmental factors."
                    )
                logger.error(error_message, exc_info=True)
                # In case of error, wait for the full cycle time to avoid spamming
                if self._running:
                    await asyncio.sleep(self._cycle)

    async def stop_scan(self):
        """Stops the scanning loop."""
        self._running = False

    def _process_advertisement(self, new_data: SwitchBotAdvertisement):
        """
        Retrieves the last known state and emits an advertisement_received
        signal with both the new and old data.
        """
        if not new_data.data:
            return

        address = new_data.address
        old_data = self._store.get_state(address)

        logger.debug(f"Received advertisement from {address}: {new_data.data}")
        advertisement_received.send(self, new_data=new_data, old_data=old_data)
