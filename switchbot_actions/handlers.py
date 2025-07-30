import asyncio
import logging
from typing import Any

from .action_runner import ActionRunnerBase, EventActionRunner, TimerActionRunner
from .config import AutomationRule
from .evaluator import StateObject
from .mqtt import mqtt_message_received
from .signals import switchbot_advertisement_received

logger = logging.getLogger(__name__)


class AutomationHandler:
    """
    Handles automation rules by dispatching signals to appropriate
    ActionRunner instances.
    """

    def __init__(self, configs: list[AutomationRule]):
        self._action_runners: list[ActionRunnerBase] = []
        for config in configs:
            source = config.if_block.source
            if source in ["switchbot", "mqtt"]:
                self._action_runners.append(EventActionRunner(config))
            elif source in ["switchbot_timer", "mqtt_timer"]:
                self._action_runners.append(TimerActionRunner(config))
            else:
                # never pass
                logger.warning(f"Unknown source '{source}' for config: {config}")

        switchbot_advertisement_received.connect(self.handle_state_change)
        mqtt_message_received.connect(self.handle_mqtt_message)

        logger.info(
            f"AutomationHandler initialized with {len(self._action_runners)} "
            "action runner(s)."
        )

    def handle_state_change(self, sender: Any, **kwargs: Any) -> None:
        """Receives state and dispatches it to all registered ActionRunners."""
        new_state: StateObject | None = kwargs.get("new_state")
        if not new_state:
            return
        asyncio.create_task(self._run_all_runners(new_state))

    def handle_mqtt_message(self, sender: Any, **kwargs: Any) -> None:
        """Receives MQTT message and dispatches it to all registered ActionRunners."""
        message: StateObject | None = kwargs.get("message")
        if not message:
            return
        asyncio.create_task(self._run_all_runners(message))

    async def _run_all_runners(self, new_state: StateObject) -> None:
        # Run all action runners concurrently
        results = await asyncio.gather(
            *[runner.run(new_state) for runner in self._action_runners],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    f"An action runner failed with an exception: {result}",
                    exc_info=True,
                )
