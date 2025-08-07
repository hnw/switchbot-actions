import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from switchbot_actions.timers import Timer


class TestTimer:
    @pytest.mark.asyncio
    async def test_timer_starts_and_calls_callback_after_duration(self):
        mock_callback = MagicMock()
        duration = 0.1
        timer = Timer(duration, mock_callback, name="test_timer")

        timer.start()
        await asyncio.sleep(duration + 0.05)  # Wait a bit longer than duration

        mock_callback.assert_called_once()  # Ensure callback was called
        assert timer._task is not None
        assert timer._task.done()  # Ensure task is done
        assert not timer._task.cancelled()  # Ensure task was not cancelled

    @pytest.mark.asyncio
    async def test_timer_can_be_stopped(self):
        mock_callback = MagicMock()
        duration = 10  # Long duration to ensure it's stopped before completion
        timer = Timer(duration, mock_callback, name="test_timer_stop")

        timer.start()
        await asyncio.sleep(0.01)  # Let the task start
        timer.stop()

        await asyncio.sleep(0.05)  # Give time for cancellation to propagate

        mock_callback.assert_not_called()
        assert timer._task is not None
        assert timer._task.done()

    @pytest.mark.asyncio
    async def test_start_does_nothing_if_timer_already_running(self, caplog):
        mock_callback = MagicMock()
        duration = 10
        timer = Timer(duration, mock_callback, name="test_timer_running")

        timer.start()
        with caplog.at_level(logging.DEBUG):
            timer.start()  # Call start again
            assert "Timer 'test_timer_running' is already running." in caplog.text

        # Ensure only one task was created
        assert timer._task is not None
        assert not timer._task.done()
        assert not timer._task.cancelled()

        timer.stop()  # Clean up the running task

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_timer_not_running(self, caplog):
        mock_callback = MagicMock()
        duration = 0.1
        timer = Timer(duration, mock_callback, name="test_timer_not_running")

        with caplog.at_level(logging.DEBUG):
            timer.stop()  # Call stop on a non-running timer
            # No log message expected for this case, as it's not an error
            assert "Timer 'test_timer_not_running' stopped." not in caplog.text

        assert timer._task is None  # No task should have been created
        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_timer_handles_cancelled_error_gracefully(self, caplog):
        mock_callback = MagicMock()
        duration = 10
        timer = Timer(duration, mock_callback, name="test_timer_cancel_error")

        timer.start()
        await asyncio.sleep(0.01)  # Let the task start

        # Manually cancel the task to simulate external cancellation
        if timer._task:
            timer._task.cancel()

        with caplog.at_level(logging.DEBUG):
            await asyncio.sleep(0.05)  # Give time for cancellation to propagate
            assert "Timer 'test_timer_cancel_error' was cancelled." in caplog.text

        mock_callback.assert_not_called()
        assert timer._task is not None
        assert timer._task.done()

    def test_timer_raises_value_error_for_invalid_duration(self):
        """Test that Timer constructor raises ValueError for non-numeric duration."""
        mock_callback = MagicMock()

        with pytest.raises(
            ValueError, match="Invalid duration_sec value: not_a_number"
        ):
            Timer("not_a_number", mock_callback, name="invalid_timer")  # type: ignore[arg-type]
