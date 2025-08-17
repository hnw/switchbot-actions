import asyncio
import logging
from typing import Any, Optional

import aiomqtt
from switchbot import SwitchBotAdvertisement

from .action_executor import create_action_executor
from .action_runner import ActionRunner
from .component import BaseComponent
from .config import AutomationSettings
from .signals import mqtt_message_received, switchbot_advertisement_received
from .state import (
    MqttState,
    RawStateEvent,
    StateSnapshot,
    SwitchBotState,
    _get_key_from_raw_event,
    create_state_object,
)
from .store import StateStore
from .triggers import DurationTrigger, EdgeTrigger

logger = logging.getLogger(__name__)
automation_logger = logging.getLogger("switchbot_actions.automation")


class AutomationHandler(BaseComponent[AutomationSettings]):
    """
    Handles automation rules by dispatching signals to appropriate
    ActionRunner instances.
    """

    def __init__(self, settings: AutomationSettings, state_store: StateStore):
        super().__init__(settings)
        self._switchbot_runners: list[ActionRunner[SwitchBotState]] = []
        self._mqtt_runners: list[ActionRunner[MqttState]] = []
        self._state_store = state_store
        self._settings = settings

        self._initialize_runners(settings)

    def _initialize_runners(self, settings: AutomationSettings):
        """Clears and re-populates the action runners from settings."""
        self._switchbot_runners.clear()
        self._mqtt_runners.clear()

        for config in settings.rules:
            executors = [
                create_action_executor(action, self._state_store)
                for action in config.then_block
            ]
            source = config.if_block.source

            if source == "switchbot":
                trigger = (
                    DurationTrigger[SwitchBotState](config.if_block)
                    if config.if_block.duration is not None
                    else EdgeTrigger[SwitchBotState](config.if_block)
                )
                self._switchbot_runners.append(
                    ActionRunner[SwitchBotState](config, executors, trigger)
                )
            elif source == "mqtt":
                trigger = (
                    DurationTrigger[MqttState](config.if_block)
                    if config.if_block.duration is not None
                    else EdgeTrigger[MqttState](config.if_block)
                )
                self._mqtt_runners.append(
                    ActionRunner[MqttState](config, executors, trigger)
                )

        logger.info(
            f"AutomationHandler initialized/updated with "
            f"{len(self._switchbot_runners)} switchbot and "
            f"{len(self._mqtt_runners)} mqtt action runner(s)."
        )

    def _is_enabled(self, settings: Optional[AutomationSettings] = None) -> bool:
        # Note: Uses provided settings or falls back to self.settings.
        # This is crucial for apply_new_settings to determine future state.
        current_settings = settings or self.settings
        return len(current_settings.rules) > 0

    async def _start(self) -> None:
        logger.info("AutomationHandler starting: connecting to signals.")
        switchbot_advertisement_received.connect(self.handle_switchbot_event)
        mqtt_message_received.connect(self.handle_mqtt_event)

    async def _stop(self) -> None:
        logger.info("AutomationHandler stopping: disconnecting from signals.")
        switchbot_advertisement_received.disconnect(self.handle_switchbot_event)
        mqtt_message_received.disconnect(self.handle_mqtt_event)

    def _require_restart(self, new_settings: AutomationSettings) -> bool:
        return False

    async def _apply_live_update(self, new_settings: AutomationSettings) -> None:
        self.logger.info("Applying live update for AutomationHandler rules.")
        switchbot_advertisement_received.disconnect(self.handle_switchbot_event)
        mqtt_message_received.disconnect(self.handle_mqtt_event)

        self._initialize_runners(new_settings)

        switchbot_advertisement_received.connect(self.handle_switchbot_event)
        mqtt_message_received.connect(self.handle_mqtt_event)

    def handle_switchbot_event(
        self, sender: Any, new_state: Optional[SwitchBotAdvertisement]
    ) -> None:
        raw_event: RawStateEvent | None = new_state
        if not raw_event:
            return
        asyncio.create_task(self._handle_event_async(raw_event))

    def handle_mqtt_event(
        self, sender: Any, message: Optional[aiomqtt.Message]
    ) -> None:
        raw_event: RawStateEvent | None = message
        if not raw_event:
            return
        asyncio.create_task(self._handle_event_async(raw_event))

    async def _handle_event_async(self, raw_event: RawStateEvent) -> None:
        all_raw_events = await self._state_store.get_all()
        devices_config = self.settings.devices
        snapshot = StateSnapshot(all_raw_events, devices_config)

        key = _get_key_from_raw_event(raw_event)
        previous_raw_event = await self._state_store.get_and_update(key, raw_event)

        previous_state_object = create_state_object(
            previous_raw_event, snapshot=snapshot
        )
        state = create_state_object(
            raw_event, previous=previous_state_object, snapshot=snapshot
        )

        if isinstance(state, SwitchBotState):
            await self._run_switchbot_runners(state)
        elif isinstance(state, MqttState):
            await self._run_mqtt_runners(state)

    def _process_runner_results(self, results: list) -> None:
        for result in results:
            if isinstance(result, ValueError):
                automation_logger.error(
                    f"Failed to execute action due to a template error: {result}"
                )
            elif isinstance(result, Exception):
                automation_logger.error(
                    "An unexpected error occurred during action execution.",
                    exc_info=result,
                )

    async def _run_switchbot_runners(self, state: SwitchBotState) -> None:
        results = await asyncio.gather(
            *[runner.run(state) for runner in self._switchbot_runners],
            return_exceptions=True,
        )
        self._process_runner_results(results)

    async def _run_mqtt_runners(self, state: MqttState) -> None:
        results = await asyncio.gather(
            *[runner.run(state) for runner in self._mqtt_runners],
            return_exceptions=True,
        )
        self._process_runner_results(results)
