import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class Timer:
    """A timer that runs a callback after a specified duration."""

    def __init__(
        self, duration_sec: float, callback: Callable, name: str = ""
    ):  # Added name for logging
        try:
            self._duration_sec = float(duration_sec)
        except ValueError as e:
            raise ValueError(
                f"Invalid duration_sec value: {duration_sec}. Must be a number."
            ) from e
        self._callback = callback
        self._name = name
        self._task: asyncio.Task | None = None

    def start(self):
        """Starts the timer."""
        if self._task and not self._task.done():
            logger.debug(f"Timer '{self._name}' is already running.")
            return

        self._task = asyncio.create_task(self._run())
        logger.debug(f"Timer '{self._name}' started for {self._duration_sec} seconds.")

    def stop(self):
        """Stops the timer."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.debug(f"Timer '{self._name}' stopped.")

    async def _run(self):
        """
        The timer's main logic.
        Waits for the duration, then calls the callback.
        """
        try:
            await asyncio.sleep(self._duration_sec)
            logger.debug(f"Timer '{self._name}' finished. Executing callback.")
            self._callback()
        except asyncio.CancelledError:
            logger.debug(f"Timer '{self._name}' was cancelled.")
