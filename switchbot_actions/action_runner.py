import asyncio
import logging
import time
from abc import ABC, abstractmethod

from pytimeparse2 import parse

from .action_executor import ActionExecutor
from .config import AutomationRule
from .evaluator import StateObject
from .timers import Timer

logger = logging.getLogger(__name__)


class ActionRunnerBase(ABC):
    def __init__(self, config: AutomationRule, executors: list[ActionExecutor]):
        self.config = config
        self.executors = executors
        self._last_run_timestamp: dict[str, float] = {}
        self._rule_conditions_met: dict[str, bool] = {}

    @abstractmethod
    async def run(self, state: StateObject) -> None:
        pass

    async def _execute_actions(self, state: StateObject) -> None:
        name = self.config.name
        logger.debug(f"Trigger '{name}' actions started for {state.id}")

        cooldown_str = self.config.cooldown
        if cooldown_str:
            duration = parse(cooldown_str)
            if duration is not None:
                if isinstance(duration, (int, float)):
                    duration_seconds = float(duration)
                else:
                    duration_seconds = duration.total_seconds()

                last_run = self._last_run_timestamp.get(state.id)
                if last_run and (time.time() - last_run < duration_seconds):
                    logger.debug(
                        f"Trigger '{name}' for {state.id} is on cooldown, skipping."
                    )
                    return

        for executor in self.executors:
            await executor.execute(state)

        self._last_run_timestamp[state.id] = time.time()


class EventActionRunner(ActionRunnerBase):
    async def run(self, state: StateObject) -> None:
        conditions_now_met = state.check_conditions(self.config.if_block)

        if conditions_now_met is None:
            return  # Skip if conditions are not applicable

        rule_conditions_previously_met = self._rule_conditions_met.get(state.id, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true (edge trigger)
            self._rule_conditions_met[state.id] = True
            await self._execute_actions(state)
        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false
            self._rule_conditions_met[state.id] = False
        # else: conditions remain true or remain false, do nothing for edge trigger


class TimerActionRunner(ActionRunnerBase):
    def __init__(self, config: AutomationRule, executors: list[ActionExecutor]):
        super().__init__(config, executors)
        self._active_timers: dict[str, Timer] = {}

    async def run(self, state: StateObject) -> None:
        name = self.config.name
        conditions_now_met = state.check_conditions(self.config.if_block)

        if conditions_now_met is None:
            return

        rule_conditions_previously_met = self._rule_conditions_met.get(state.id, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true, start timer
            self._rule_conditions_met[state.id] = True
            duration = self.config.if_block.duration

            assert duration is not None, "Duration must be set for timer-based rules"

            timer = Timer(
                duration,
                lambda: asyncio.create_task(self._timer_callback(state)),
                name=f"Rule {name} Timer for {state.id}",
            )
            self._active_timers[state.id] = timer
            timer.start()
            logger.debug(
                f"Timer started for rule {name} for {duration} seconds on {state.id}."
            )

        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false, stop timer
            self._rule_conditions_met[state.id] = False
            if state.id in self._active_timers:
                self._active_timers[state.id].stop()
                del self._active_timers[state.id]
                logger.debug(f"Timer cancelled for rule {name} on {state.id}.")

    async def _timer_callback(self, state: StateObject) -> None:
        """Called when the timer completes."""
        await self._execute_actions(state)
        if state.id in self._active_timers:
            del self._active_timers[state.id]  # Clear the timer after execution
