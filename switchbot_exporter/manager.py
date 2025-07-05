# switchbot_exporter/manager.py
import asyncio
import logging
from switchbot import (
    GetSwitchbotDevices,
    SwitchBotAdvertisement,
)
from .signals import advertisement_received

logger = logging.getLogger(__name__)

class SwitchbotManager:
    """
    Manages the scanning for SwitchBot devices and dispatches signals
    when new advertisement data is received.
    """
    def __init__(self, scanner: GetSwitchbotDevices, scan_interval: int = 10):
        self._scan_interval = scan_interval
        self._scanner = scanner
        self._running = False

    async def start_scan(self):
        """Starts the continuous scanning loop for SwitchBot devices."""
        self._running = True
        while self._running:
            try:
                devices = await self._scanner.discover()
                await asyncio.sleep(self._scan_interval)

                for address, device in devices.items():
                    self._process_advertisement(device)

            except Exception as e:
                logger.error(f"Error during BLE scan: {e}", exc_info=True)
                await asyncio.sleep(self._scan_interval)

    async def stop_scan(self):
        """Stops the scanning loop."""
        self._running = False
        if self._scanner._scanner and self._scanner._scanner.is_scanning:
             await self._scanner.stop()

    def _process_advertisement(self, advertisement: SwitchBotAdvertisement):
        """Parses advertisement data and sends a signal."""
        if advertisement.data:
            logger.debug(f"Received advertisement from {advertisement.address}: {advertisement.data}")
            advertisement_received.send(self, device_data=advertisement)
