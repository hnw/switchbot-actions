import asyncio
import logging
from typing import Any

from .action_executor import create_action_executor
from .action_runner import ActionRunner
from .config import AutomationRule
from .signals import mqtt_message_received, switchbot_advertisement_received
from .state import (
    MqttState,
    RawStateEvent,
    SwitchBotState,
    _get_key_from_raw_event,
    create_state_object_with_previous,
)
from .store import StateStore
from .triggers import DurationTrigger, EdgeTrigger

logger = logging.getLogger(__name__)


class AutomationHandler:
    """
    Handles automation rules by dispatching signals to appropriate
    ActionRunner instances.
    """

    def __init__(self, configs: list[AutomationRule], state_store: StateStore):
        self._switchbot_runners: list[ActionRunner[SwitchBotState]] = []
        self._mqtt_runners: list[ActionRunner[MqttState]] = []
        self._state_store = state_store

        for config in configs:
            executors = [
                create_action_executor(action, state_store)
                for action in config.then_block
            ]
            source = config.if_block.source

            if source in ["switchbot", "switchbot_timer"]:
                if source == "switchbot":
                    trigger = EdgeTrigger[SwitchBotState](config.if_block)
                else:
                    trigger = DurationTrigger[SwitchBotState](config.if_block)
                self._switchbot_runners.append(
                    ActionRunner[SwitchBotState](config, executors, trigger)
                )
            elif source in ["mqtt", "mqtt_timer"]:
                if source == "mqtt":
                    trigger = EdgeTrigger[MqttState](config.if_block)
                else:
                    trigger = DurationTrigger[MqttState](config.if_block)
                self._mqtt_runners.append(
                    ActionRunner[MqttState](config, executors, trigger)
                )
            else:
                logger.warning(f"Unknown source '{source}' for config: {config}")
                continue

        logger.info(
            f"AutomationHandler initialized with "
            f"{len(self._switchbot_runners)} switchbot and "
            f"{len(self._mqtt_runners)} mqtt action runner(s)."
        )
        switchbot_advertisement_received.connect(self.handle_switchbot_event)
        mqtt_message_received.connect(self.handle_mqtt_event)

    def handle_switchbot_event(self, sender: Any, **kwargs: Any) -> None:
        """Receives SwitchBot state and dispatches it to appropriate ActionRunners."""
        raw_state: RawStateEvent | None = kwargs.get("new_state")
        if not raw_state:
            return
        asyncio.create_task(self._handle_switchbot_event_async(new_state=raw_state))

    def handle_mqtt_event(self, sender: Any, **kwargs: Any) -> None:
        """Receives MQTT message and dispatches it to appropriate ActionRunners."""
        raw_message: RawStateEvent | None = kwargs.get("message")
        if not raw_message:
            return
        asyncio.create_task(self._handle_mqtt_event_async(message=raw_message))

    async def _handle_switchbot_event_async(self, **kwargs: Any) -> None:
        """Receives SwitchBot state and dispatches it to appropriate ActionRunners."""
        raw_state: RawStateEvent | None = kwargs.get("new_state")
        if not raw_state:
            return

        key = _get_key_from_raw_event(raw_state)
        previous_raw_event = await self._state_store.get_and_update(key, raw_state)
        state = create_state_object_with_previous(raw_state, previous_raw_event)

        if isinstance(state, SwitchBotState):
            await self._run_switchbot_runners(state)
        else:
            logger.warning(
                f"Received non-SwitchBotState for switchbot event: {type(state)}"
            )

    async def _handle_mqtt_event_async(self, **kwargs: Any) -> None:
        """Receives MQTT message and dispatches it to appropriate ActionRunners."""
        raw_message: RawStateEvent | None = kwargs.get("message")
        if not raw_message:
            return

        key = _get_key_from_raw_event(raw_message)
        previous_raw_message = await self._state_store.get_and_update(key, raw_message)
        state = create_state_object_with_previous(raw_message, previous_raw_message)

        if isinstance(state, MqttState):
            await self._run_mqtt_runners(state)
        else:
            logger.warning(f"Received non-MqttState for MQTT event: {type(state)}")

    async def _run_switchbot_runners(self, state: SwitchBotState) -> None:
        results = await asyncio.gather(
            *[runner.run(state) for runner in self._switchbot_runners],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    f"An action runner failed with an exception: {result}",
                    exc_info=True,
                )

    async def _run_mqtt_runners(self, state: MqttState) -> None:
        results = await asyncio.gather(
            *[runner.run(state) for runner in self._mqtt_runners],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    f"An action runner failed with an exception: {result}",
                    exc_info=True,
                )
