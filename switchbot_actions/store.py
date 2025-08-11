# switchbot_actions/store.py
import logging
from asyncio import Lock
from typing import TypeAlias, Union

import aiomqtt
from switchbot import SwitchBotAdvertisement

RawStateEvent: TypeAlias = Union[SwitchBotAdvertisement, aiomqtt.Message]

logger = logging.getLogger(__name__)


class StateStore:
    """
    An in-memory, thread-safe store for the latest state of each entity.
    """

    def __init__(self):
        self._states: dict[str, RawStateEvent] = {}
        self._lock = Lock()

    async def get(self, key: str) -> RawStateEvent | None:
        """
        Retrieves the latest raw event for a specific key.
        Returns None if no state is associated with the key.
        """
        async with self._lock:
            return self._states.get(key)

    async def get_and_update(
        self, key: str, new_raw_event: RawStateEvent
    ) -> RawStateEvent | None:
        """
        Atomically retrieves the old raw event for a specific key and updates it with
        the new raw event.
        Returns the old raw event, or None if no state was previously associated with
        the key.
        """
        async with self._lock:
            old_raw_event = self._states.get(key)
            self._states[key] = new_raw_event
            logger.debug(f"State atomically retrieved and updated for key {key}")
            return old_raw_event

    async def get_all(self) -> dict[str, RawStateEvent]:
        """
        Retrieves a copy of the raw events of all entities.
        """
        async with self._lock:
            return self._states.copy()
