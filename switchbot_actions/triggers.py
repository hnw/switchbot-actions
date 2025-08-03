import asyncio
import logging
import operator
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Optional, TypeVar

from .config import AutomationIf
from .evaluator import StateObject
from .timers import Timer

logger = logging.getLogger(__name__)

OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def _evaluate_single_condition(condition: str, new_value: Any) -> bool:
    """Evaluates a single state condition."""
    parts = str(condition).split(" ", 1)
    op_str = "=="
    val_str = str(condition)

    if len(parts) == 2 and parts[0] in OPERATORS:
        op_str = parts[0]
        val_str = parts[1]

    op = OPERATORS.get(op_str, operator.eq)

    try:
        if new_value is None:
            return False
        if isinstance(new_value, bool):
            expected_value = val_str.lower() in ("true", "1", "t", "y", "yes")
        elif isinstance(new_value, str):
            expected_value = val_str
        else:
            expected_value = type(new_value)(val_str)
        return op(new_value, expected_value)
    except (ValueError, TypeError):
        return False


T = TypeVar("T", bound=StateObject)


class Trigger(ABC, Generic[T]):
    def __init__(self, if_config: AutomationIf):
        self._if_config = if_config
        self._callback: Callable[[T], Any] | None = None
        self._rule_conditions_met: dict[str, bool] = {}

    def set_callback(self, callback: Callable[[T], Any]):
        self._callback = callback

    def _check_all_conditions(self, state: T) -> Optional[bool]:
        """
        Checks if the given conditions are met by the current state.
        Returns True if all conditions are met, False if any condition is not met,
        and None if the state does not match the expected source or topic.
        """
        all_values = state.get_values_dict()

        # Evaluate conditions
        for key, condition in self._if_config.conditions.items():
            if key not in all_values:
                return None  # Return None if the key is not found in state data
            value_to_check = all_values.get(key)
            if not _evaluate_single_condition(str(condition), value_to_check):
                return False
        return True

    @abstractmethod
    async def process_state(self, state: T) -> None:
        pass


class EdgeTrigger(Trigger[T]):
    async def process_state(self, state: T) -> None:
        conditions_now_met = self._check_all_conditions(state)

        if conditions_now_met is None:
            return

        rule_conditions_previously_met = self._rule_conditions_met.get(state.id, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true (edge trigger)
            self._rule_conditions_met[state.id] = True
            if self._callback:
                await self._callback(state)
        elif not conditions_now_met and rule_conditions_previously_met:
            # Conditions just became false
            self._rule_conditions_met[state.id] = False


class DurationTrigger(Trigger[T]):
    def __init__(self, if_config: AutomationIf):
        super().__init__(if_config)
        self._active_timers: dict[str, Timer] = {}

    async def process_state(self, state: T) -> None:
        name = self._if_config.name
        conditions_now_met = self._check_all_conditions(state)

        if conditions_now_met is None:
            return

        rule_conditions_previously_met = self._rule_conditions_met.get(state.id, False)

        if conditions_now_met and not rule_conditions_previously_met:
            # Conditions just became true, start timer
            self._rule_conditions_met[state.id] = True
            duration = self._if_config.duration

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

    async def _timer_callback(self, state: T) -> None:
        """Called when the timer completes."""
        try:
            if self._callback:
                await self._callback(state)
        finally:
            if state.id in self._active_timers:
                del self._active_timers[state.id]  # Clear the timer after execution
