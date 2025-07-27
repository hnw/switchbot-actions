import asyncio
import logging
import time
from abc import ABC, abstractmethod

from pytimeparse2 import parse

from .action_executor import execute_action
from .config import AutomationRule
from .evaluator import StateObject, check_conditions, get_state_key
from .timers import Timer

logger = logging.getLogger(__name__)


class ActionRunnerBase(ABC):
    def __init__(self, config: AutomationRule):
        self.config = config
        self._last_run_timestamp: dict[str, float] = {}
        self._rule_conditions_met: dict[str, bool] = {}

    @abstractmethod
    async def run(self, state: StateObject) -> None:
        pass

    async def _execute_actions(self, state: StateObject) -> None:
        name = self.config.name
        state_key = get_state_key(state)
        logger.debug(f"Trigger '{name}' actions started for state key {state_key}")

        cooldown_str = self.config.cooldown
        if cooldown_str:
            duration = parse(cooldown_str)
            if duration is not None:
                if isinstance(duration, (int, float)):
                    duration_seconds = float(duration)
                else:
                    duration_seconds = duration.total_seconds()

                last_run = self._last_run_timestamp.get(state_key)
                if last_run and (time.time() - last_run < duration_seconds):
                    logger.debug(
                        f"Trigger '{name}' for state key {state_key} "
                        "is on cooldown, skipping."
                    )
                    return

        for action in self.config.then_block:
            await execute_action(action, state)

        self._last_run_timestamp[state_key] = time.time()


class EventActionRunner(ActionRunnerBase):
    async def run(self, state: StateObject) -> None:
        conditions_now_met = check_conditions(self.config.if_block, state)
        state_key = get_state_key(state)

        if conditions_now_met is None:
            return  # Skip if conditions are not applicable

        rule_conditions_previously_met = self._rule_conditions_met.get(state_key, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true (edge trigger)
            self._rule_conditions_met[state_key] = True
            await self._execute_actions(state)
        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false
            self._rule_conditions_met[state_key] = False
        # else: conditions remain true or remain false, do nothing for edge trigger


class TimerActionRunner(ActionRunnerBase):
    def __init__(self, config: AutomationRule):
        super().__init__(config)
        self._active_timers: dict[str, Timer] = {}

    async def run(self, state: StateObject) -> None:
        name = self.config.name
        conditions_now_met = check_conditions(self.config.if_block, state)

        state_key = get_state_key(state)

        if conditions_now_met is None:
            return

        rule_conditions_previously_met = self._rule_conditions_met.get(state_key, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true, start timer
            self._rule_conditions_met[state_key] = True
            duration = self.config.if_block.duration

            assert duration is not None, "Duration must be set for timer-based rules"

            timer = Timer(
                duration,
                lambda: asyncio.create_task(self._timer_callback(state)),
                name=f"Rule {name} Timer for {state_key}",
            )
            self._active_timers[state_key] = timer
            timer.start()
            logger.debug(
                f"Timer started for rule {name} "
                f"for {duration} seconds on device {state_key}."
            )

        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false, stop timer
            self._rule_conditions_met[state_key] = False
            if state_key in self._active_timers:
                self._active_timers[state_key].stop()
                del self._active_timers[state_key]
                logger.debug(f"Timer cancelled for rule {name} on device {state_key}.")

    async def _timer_callback(self, state: StateObject) -> None:
        """Called when the timer completes."""
        state_key = get_state_key(state)
        await self._execute_actions(state)
        if state_key in self._active_timers:
            del self._active_timers[state_key]  # Clear the timer after execution
