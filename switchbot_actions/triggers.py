import asyncio
import logging
import operator
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Optional, TypeVar, cast

from .config import AutomationIf
from .state import StateObject
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
        self._action: Callable[[T], Any] | None = None

    def on_triggered(self, action: Callable[[T], Any]):
        self._action = action

    def _check_all_conditions(self, state: T) -> Optional[bool]:
        """
        Checks if the given conditions are met by the current state.
        Returns True if all conditions are met, False if any condition is not met,
        and None if the state does not match the expected source or topic.
        """
        for key, condition_value in self._if_config.conditions.items():
            target_obj = state
            attr_name = key

            if key.startswith("previous."):
                if state.previous is None:
                    return False  # previous state required but not available
                target_obj = state.previous
                attr_name = key.split(".", 1)[1]

            try:
                value_to_check = getattr(target_obj, attr_name)
            except AttributeError:
                return None  # Attribute not found on state or previous state

            # Format the condition value string (RHS) using the current state
            formatted_condition_value = state.format(str(condition_value))

            if not _evaluate_single_condition(
                formatted_condition_value, value_to_check
            ):
                return False

        return True

    @abstractmethod
    async def process_state(self, state: T) -> None:
        pass


class EdgeTrigger(Trigger[T]):
    async def process_state(self, state: T) -> None:
        if state.previous is None:
            # No previous state, cannot detect an edge
            return

        conditions_met_now = self._check_all_conditions(state)
        conditions_met_before = self._check_all_conditions(cast(T, state.previous))

        if conditions_met_now and not conditions_met_before:
            # Conditions just became true (rising edge)
            if self._action:
                await self._action(state)


class DurationTrigger(Trigger[T]):
    def __init__(self, if_config: AutomationIf):
        super().__init__(if_config)
        self._active_timers: dict[str, Timer] = {}
        self._rule_conditions_met: dict[str, bool] = {}

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
            if self._action:
                await self._action(state)
        finally:
            if state.id in self._active_timers:
                del self._active_timers[state.id]  # Clear the timer after execution
