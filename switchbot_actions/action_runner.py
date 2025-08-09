import logging
import time
from typing import Generic, TypeVar

from pytimeparse2 import parse

from .action_executor import ActionExecutor
from .config import AutomationRule
from .state import StateObject
from .triggers import Trigger

logger = logging.getLogger("switchbot_actions.automation")

T = TypeVar("T", bound=StateObject)


class ActionRunner(Generic[T]):
    def __init__(
        self,
        config: AutomationRule,
        executors: list[ActionExecutor],
        trigger: Trigger[T],
    ):
        self._config = config
        self._executors = executors
        self._trigger = trigger
        self._last_run_timestamp: dict[str, float] = {}
        self._trigger.on_triggered(self.execute_actions)

    async def run(self, state: T) -> None:
        await self._trigger.process_state(state)

    async def execute_actions(self, state: T) -> None:
        name = self._config.name
        logger.debug(
            f"Rule '{name}' triggered. Executing actions for device {state.id}"
        )

        cooldown_str = self._config.cooldown
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

        for executor in self._executors:
            await executor.execute(state)

        self._last_run_timestamp[state.id] = time.time()
