import asyncio
import logging

from switchbot import (
    GetSwitchbotDevices,
    SwitchBotAdvertisement,
)

from .config import ScannerSettings
from .signals import switchbot_advertisement_received

logger = logging.getLogger(__name__)


class SwitchbotScanner:
    """
    Continuously scans for SwitchBot BLE advertisements and serves as the
    central publisher of device events.
    """

    def __init__(
        self,
        settings: ScannerSettings,
        scanner: GetSwitchbotDevices | None = None,
    ):
        if scanner is None:
            self._scanner = GetSwitchbotDevices(interface=settings.interface)
        else:
            self._scanner = scanner
        self._cycle = settings.cycle
        self._duration = settings.duration
        self._running = False
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        """Starts the scanner component and its background task."""
        if self._running:
            logger.warning("Scanner is already running.")
            return
        logger.info("Starting SwitchBot BLE scanner...")
        self._running = True
        self.task = asyncio.create_task(self._scan_loop())

    async def stop(self) -> None:
        """Stops the scanner component and its background task."""
        if not self._running or not self.task:
            logger.warning("Scanner is not running.")
            return
        logger.info("Stopping SwitchBot BLE scanner...")
        self._running = False
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            logger.info("Scanner task successfully cancelled.")
        self.task = None

    async def _scan_loop(self) -> None:
        """The continuous scanning loop for SwitchBot devices."""
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

    def _process_advertisement(self, new_state: SwitchBotAdvertisement) -> None:
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
