import asyncio
import logging
import time
from abc import ABC, abstractmethod

from pytimeparse2 import parse

from .action_executor import execute_action
from .evaluator import StateObject, check_conditions, get_state_key
from .timers import Timer

logger = logging.getLogger(__name__)


class ActionRunnerBase(ABC):
    def __init__(self, config: dict):
        self.config = config
        self._last_run_timestamp: dict[str, float] = {}
        self._rule_conditions_met: dict[str, bool] = {}

    @abstractmethod
    async def run(self, state: StateObject):
        pass

    async def _execute_actions(self, state: StateObject):
        name = self.config.get("name", "Unnamed Trigger")
        state_key = get_state_key(state)
        logger.debug(f"Trigger '{name}' actions started for state key {state_key}")

        cooldown_str = self.config.get("cooldown")
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

        for action in self.config.get("then", []):
            await execute_action(action, state)

        self._last_run_timestamp[state_key] = time.time()


class EventActionRunner(ActionRunnerBase):
    async def run(self, state: StateObject):
        if_config = self.config.get("if", {})
        conditions_now_met = check_conditions(if_config, state)
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
    def __init__(self, config: dict):
        super().__init__(config)
        self._active_timers: dict[str, Timer] = {}

    async def run(self, state: StateObject):
        if_config = self.config.get("if", {})
        conditions_now_met = check_conditions(if_config, state)
        state_key = get_state_key(state)

        if conditions_now_met is None:
            return

        rule_conditions_previously_met = self._rule_conditions_met.get(state_key, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true, start timer
            self._rule_conditions_met[state_key] = True
            duration_str = if_config.get("duration")
            if not duration_str:
                logger.error(
                    f"Rule {self.config.get('name', id(self.config))} has no duration."
                )
                return

            duration = parse(duration_str)
            if duration is None:
                logger.error(
                    f"Invalid duration '{duration_str}' for rule "
                    f"{self.config.get('name', id(self.config))}."
                )
                return

            if isinstance(duration, (int, float)):
                duration_sec = float(duration)
            else:
                duration_sec = duration.total_seconds()

            timer = Timer(
                duration_sec,
                lambda: asyncio.create_task(self._timer_callback(state)),
                name=f"Rule {self.config.get('name', id(self.config))} "
                f"Timer for {state_key}",
            )
            self._active_timers[state_key] = timer
            timer.start()
            logger.debug(
                f"Timer started for rule {self.config.get('name', id(self.config))} "
                f"for {duration_sec} seconds on device {state_key}."
            )

        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false, stop timer
            self._rule_conditions_met[state_key] = False
            if state_key in self._active_timers:
                self._active_timers[state_key].stop()
                del self._active_timers[state_key]
                logger.debug(
                    f"Timer cancelled for rule "
                    f"{self.config.get('name', id(self.config))} on device {state_key}."
                )

    async def _timer_callback(self, state: StateObject):
        """Called when the timer completes."""
        state_key = get_state_key(state)
        await self._execute_actions(state)
        if state_key in self._active_timers:
            del self._active_timers[state_key]  # Clear the timer after execution
