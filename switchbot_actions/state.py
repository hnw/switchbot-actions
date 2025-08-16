from __future__ import annotations

import json
import logging
import string
from abc import ABC, abstractmethod
from typing import (
    Any,
    Dict,
    Generic,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
    Union,
    overload,
)

import aiomqtt
from switchbot import SwitchBotAdvertisement

from .config import DeviceSettings
from .store import RawStateEvent

T_State = TypeVar("T_State", bound=RawStateEvent)

logger = logging.getLogger(__name__)

_empty_state_instance: "StateObject"


class TemplateFormatter(string.Formatter):
    """
    Custom formatter to implement a prioritized lookup for template variables.
    The resolution order is:
    1. Special keywords (e.g., 'previous').
    2. Keys of the trigger device itself (e.g., 'temperature').
    3. Device aliases defined in the configuration.
    """

    def get_value(
        self, key: Union[int, str], args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> Any:
        if isinstance(key, int):
            return args[key]  # Standard behavior for positional arguments

        # Custom key resolution based on priority
        current_data = kwargs.get("__current_data__")
        snapshot = kwargs.get("snapshot")

        # Priority 1: Special keywords (currently only 'previous')
        if key == "previous":
            return kwargs["previous"]

        # Priority 2: Trigger device's own keys
        if current_data and hasattr(current_data, key):
            return getattr(current_data, key)

        # Priority 3: Device aliases from the snapshot
        if snapshot and hasattr(snapshot, key):
            return getattr(snapshot, key)

        # Fallback for any other keys that might be in the context
        if key in kwargs:
            return kwargs[key]

        raise KeyError(key)

    def get_field(
        self, field_name: str, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> tuple[Any, str]:
        value, key = super().get_field(field_name, args, kwargs)

        if callable(value):
            raise AttributeError(f"method access is not allowed: {field_name}")

        return value, key


class StateSnapshot:
    """
    A snapshot of all device states at a specific moment, providing access
    to individual device states via their aliases.
    """

    def __init__(
        self,
        raw_events: dict[str, RawStateEvent],
        devices_config: dict[str, DeviceSettings],
    ):
        self._raw_events = raw_events
        self._devices_config = devices_config
        self._cache: dict[str, "StateObject"] = {}

    def __getattr__(self, alias: str) -> "StateObject":
        if alias in self._cache:
            return self._cache[alias]

        device_config = self._devices_config.get(alias)
        if not device_config or not device_config.address:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{alias}'"
            ) from None

        raw_event = self._raw_events.get(device_config.address)
        if not raw_event:
            self._cache[alias] = _empty_state_instance
            return _empty_state_instance

        # Pass self to the created state object to allow chained lookups,
        # but without a 'previous' state.
        state_object = create_state_object(raw_event, previous=None, snapshot=self)
        self._cache[alias] = state_object
        return state_object


class StateObject(ABC, Generic[T_State]):
    def __init__(
        self,
        raw_event: T_State,
        previous: Optional["StateObject"] = None,
        snapshot: Optional[StateSnapshot] = None,
    ):
        self._raw_event = raw_event
        self._cached_values = None
        self.previous = previous if previous else _empty_state_instance
        self.snapshot = snapshot

    def __bool__(self) -> bool:
        return True

    def __getattr__(self, name: str) -> Any:
        try:
            return self.get_values_dict()[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from None

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def _get_values_as_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get_values_dict(self) -> Dict[str, Any]:
        if self._cached_values is None:
            self._cached_values = self._get_values_as_dict()
        return self._cached_values

    @overload
    def format(self, template_data: str) -> str: ...

    @overload
    def format(self, template_data: Dict[str, Any]) -> Dict[str, Any]: ...

    def format(
        self, template_data: Union[str, Dict[str, Any]]
    ) -> Union[str, Dict[str, Any]]:
        context = {
            "__current_data__": self,
            "previous": self.previous,
            "snapshot": self.snapshot,
        }
        if isinstance(template_data, dict):
            return {k: self.format(str(v)) for k, v in template_data.items()}
        else:
            try:
                return _template_formatter.format(str(template_data), **context)
            except AttributeError as e:
                raise ValueError(f"Invalid attribute access in placeholder: {e}") from e
            except KeyError as e:
                key_name = e.args[0]
                raise ValueError(
                    f"Placeholder '{key_name}' could not be resolved. The key name is"
                    " likely incorrect."
                ) from e


class _NullState(StateObject):
    """A placeholder for a non-existent state, returning itself on attr access."""

    def __init__(self):
        # Note: No call to super().__init__ is needed here as we are overriding
        # all necessary attributes and methods.
        self._raw_event = None
        self.previous = self
        self.snapshot = None

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        # Return self to allow chained attribute access on an empty state,
        # e.g., {non_existent_device.temperature}, which will resolve to "".
        return self

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return "EmptyState"

    @property
    def id(self) -> str:
        return ""

    def _get_values_as_dict(self) -> Dict[str, Any]:
        return {}


_template_formatter = TemplateFormatter()
_empty_state_instance = _NullState()


class SwitchBotState(StateObject[SwitchBotAdvertisement]):
    @property
    def id(self) -> str:
        return self._raw_event.address

    def _get_values_as_dict(self) -> Dict[str, Any]:
        state = self._raw_event
        flat_data = state.data.get("data", {})
        for key, value in state.data.items():
            if key != "data":
                flat_data[key] = value
        if hasattr(state, "address"):
            flat_data["address"] = state.address
        if hasattr(state, "rssi"):
            flat_data["rssi"] = state.rssi
        return flat_data


class MqttState(StateObject[aiomqtt.Message]):
    @property
    def id(self) -> str:
        return str(self._raw_event.topic)

    def _get_values_as_dict(self) -> Dict[str, Any]:
        state = self._raw_event
        if isinstance(state.payload, bytes):
            payload_decoded = state.payload.decode()
        else:
            payload_decoded = str(state.payload)

        format_data = {"topic": str(state.topic), "payload": payload_decoded}
        try:
            payload_json = json.loads(payload_decoded)
            if isinstance(payload_json, dict):
                format_data.update(payload_json)
        except json.JSONDecodeError:
            pass
        return format_data


def create_state_object(
    raw_event: Optional[RawStateEvent],
    previous: Optional[StateObject] = None,
    snapshot: Optional[StateSnapshot] = None,
) -> StateObject:
    if raw_event is None:
        return _empty_state_instance
    if isinstance(raw_event, SwitchBotAdvertisement):
        return SwitchBotState(raw_event, previous=previous, snapshot=snapshot)
    elif isinstance(raw_event, aiomqtt.Message):
        return MqttState(raw_event, previous=previous, snapshot=snapshot)
    raise TypeError(f"Unsupported event type: {type(raw_event)}")


def _get_key_from_raw_event(raw_event: RawStateEvent) -> str:
    if isinstance(raw_event, SwitchBotAdvertisement):
        return raw_event.address
    elif isinstance(raw_event, aiomqtt.Message):
        return str(raw_event.topic)
    raise TypeError(f"Unsupported event type for key extraction: {type(raw_event)}")
