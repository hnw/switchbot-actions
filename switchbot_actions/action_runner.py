import logging
import time
from typing import Generic, TypeVar

from pytimeparse2 import parse

from .action_executor import ActionExecutor
from .config import AutomationRule
from .evaluator import StateObject
from .triggers import Trigger

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=StateObject)


class ActionRunner(Generic[T]):
    def __init__(
        self,
        config: AutomationRule,
        executors: list[ActionExecutor],
        trigger: Trigger[T],
    ):
        self.config = config
        self.executors = executors
        self.trigger = trigger
        self._last_run_timestamp: dict[str, float] = {}
        self.trigger.set_callback(self._execute_actions)

    async def run(self, state: T) -> None:
        await self.trigger.process_state(state)

    async def _execute_actions(self, state: T) -> None:
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
