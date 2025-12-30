import asyncio
import logging
import time
from typing import Optional

from switchbot import GetSwitchbotDevices, SwitchBotAdvertisement

from .component import BaseComponent
from .config import ScannerSettings
from .signals import scan_executed, switchbot_advertisement_received

logger = logging.getLogger(__name__)


class SwitchbotScanner(BaseComponent[ScannerSettings]):
    """
    Continuously scans for SwitchBot BLE advertisements and serves as the
    central publisher of device events.
    """

    def __init__(
        self,
        settings: ScannerSettings,
        scanner: GetSwitchbotDevices | None = None,
    ):
        super().__init__(settings)
        if scanner is None:
            self._scanner = GetSwitchbotDevices(interface=self.settings.interface)
        else:
            self._scanner = scanner
        self.task: asyncio.Task | None = None

    def _is_enabled(self, settings: Optional[ScannerSettings] = None) -> bool:
        """Checks if the scanner is enabled based on settings."""
        current_settings = settings or self.settings
        return current_settings.enabled

    async def _start(self) -> None:
        """Starts the scanner component's background task."""
        self.task = asyncio.create_task(self._scan_loop())

    async def _stop(self) -> None:
        """Stops the scanner component's background task."""
        if not self.task:
            return

        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            logger.info("Scanner task successfully cancelled.")
        self.task = None

    def _require_restart(self, new_settings: ScannerSettings) -> bool:
        """
        Determines if a restart is required for the scanner based on new settings.
        A restart is required if the Bluetooth interface changes.
        """
        return self.settings.interface != new_settings.interface

    async def _apply_live_update(self, new_settings: ScannerSettings) -> None:
        """
        Applies live updates to scanner settings (cycle and duration).
        These changes will be picked up by the scanning loop in its next iteration.
        """
        # The _scan_loop directly references self.settings.cycle and .duration.
        # By updating self.settings in apply_new_settings (in BaseComponent),
        # the loop will automatically use the new values in its next iteration.
        # No explicit action is needed here.
        pass

    async def _scan_loop(self) -> None:
        """The continuous scanning loop for SwitchBot devices."""
        last_scan_start = None
        cycle_duration = None
        while True:
            try:
                now = time.monotonic()
                if last_scan_start is not None:
                    cycle_duration = now - last_scan_start
                last_scan_start = now

                logger.debug(
                    f"Starting BLE scan for {self.settings.duration} seconds..."
                )
                start_time = time.monotonic()
                devices = await self._scanner.discover(
                    scan_timeout=self.settings.duration
                )
                scan_duration = time.monotonic() - start_time

                scan_executed.send(
                    self,
                    interface=self.settings.interface,
                    scan_duration=scan_duration,
                    cycle_duration=cycle_duration,
                )

                for address, device in devices.items():
                    self._process_advertisement(device)

                # Wait for the configured wait time
                if self._running and self.settings.wait > 0:
                    logger.debug(
                        f"Scan finished, waiting for {self.settings.wait} seconds."
                    )
                    await asyncio.sleep(self.settings.wait)

            except Exception as e:
                message, is_known_error = self._format_ble_error_message(e)
                if is_known_error:
                    logger.error(message)
                else:
                    logger.error(message, exc_info=True)
                # In case of error, wait for the configured wait time to avoid spamming
                if self._running:
                    await asyncio.sleep(self.settings.wait)

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
