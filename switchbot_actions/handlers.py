import asyncio
import logging

from .action_runner import ActionRunnerBase, EventActionRunner, TimerActionRunner
from .evaluator import StateObject
from .signals import state_changed

logger = logging.getLogger(__name__)


class AutomationHandler:
    """
    Handles automation rules by dispatching signals to appropriate
    ActionRunner instances.
    """

    def __init__(self, configs: list):
        self._action_runners: list[ActionRunnerBase] = []
        for config in configs:
            source = config.get("if", {}).get("source")
            if source == "switchbot":
                self._action_runners.append(EventActionRunner(config))
            elif source == "switchbot_timer":
                self._action_runners.append(TimerActionRunner(config))
            else:
                logger.warning(f"Unknown source '{source}' for config: {config}")
        state_changed.connect(self.handle_signal)
        logger.info(
            f"AutomationHandler initialized with {len(self._action_runners)} "
            "action runner(s)."
        )

    def handle_signal(self, sender, **kwargs):
        """Receives state and dispatches it to all registered ActionRunners."""
        new_state: StateObject | None = kwargs.get("new_state")
        if not new_state:
            return
        asyncio.create_task(self._run_all_runners(new_state))

    async def _run_all_runners(self, new_state: StateObject):
        # Run all action runners concurrently
        await asyncio.gather(
            *[runner.run(new_state) for runner in self._action_runners]
        )
