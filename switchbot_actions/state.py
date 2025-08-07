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

from .store import RawStateEvent

T_State = TypeVar("T_State", bound=RawStateEvent)

logger = logging.getLogger(__name__)


class TemplateFormatter(string.Formatter):
    def get_field(
        self, field_name: str, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> tuple[Any, str]:
        """
        Implements a prioritized lookup for template variables.

        - Dotted names (e.g., 'previous.temperature') are resolved as attributes.
        - Top-level names (e.g., 'temperature') are first resolved as attributes
          on a special '__current_data__' object, falling back to the main context.
        """
        if "." in field_name:
            value, key = super().get_field(field_name, args, kwargs)
        else:
            current_data = kwargs.get("__current_data__")
            if current_data and hasattr(current_data, field_name):
                value = getattr(current_data, field_name)
            elif field_name in kwargs:
                value = kwargs[field_name]
            else:
                raise KeyError(field_name)
            key = field_name

        if callable(value):
            raise AttributeError(f"method access is not allowed: {field_name}")

        return value, key


class _EmptyState:
    """A placeholder for a non-existent previous state."""

    def __getattr__(self, name: str) -> str:
        return ""


_empty_state_instance = _EmptyState()


class StateObject(ABC, Generic[T_State]):
    def __init__(self, raw_event: T_State, previous: Optional["StateObject"] = None):
        self._raw_event: T_State = raw_event
        self._cached_values: Dict[str, Any] | None = None
        self.previous: Optional["StateObject"] = previous

    def __getattr__(self, name: str) -> Any:
        try:
            return self.get_values_dict()[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

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
            "previous": self.previous if self.previous else _empty_state_instance,
        }
        formatter = TemplateFormatter()

        if isinstance(template_data, dict):
            return {k: self.format(str(v)) for k, v in template_data.items()}
        else:
            try:
                return formatter.format(str(template_data), **context)
            except AttributeError as e:
                # {previous.temprature} や {previous.format} のようなケース
                raise ValueError(f"Invalid attribute access in placeholder: {e}") from e
            except KeyError as e:
                # {temprature} のようなケース
                key_name = e.args[0]
                raise ValueError(
                    f"Placeholder '{key_name}' could not be resolved. The key name is"
                    " likely incorrect."
                ) from e


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
    raw_event: RawStateEvent, previous: Optional[StateObject] = None
) -> StateObject:
    if isinstance(raw_event, SwitchBotAdvertisement):
        return SwitchBotState(raw_event, previous=previous)
    elif isinstance(raw_event, aiomqtt.Message):
        return MqttState(raw_event, previous=previous)
    raise TypeError(f"Unsupported event type: {type(raw_event)}")


def _get_key_from_raw_event(raw_event: RawStateEvent) -> str:
    if isinstance(raw_event, SwitchBotAdvertisement):
        return raw_event.address
    elif isinstance(raw_event, aiomqtt.Message):
        return str(raw_event.topic)
    raise TypeError(f"Unsupported event type for key extraction: {type(raw_event)}")


def create_state_object_with_previous(
    new_raw_event: RawStateEvent, previous_raw_event: Optional[RawStateEvent]
) -> StateObject:
    previous_state_object: Optional[StateObject] = None
    if previous_raw_event:
        previous_state_object = create_state_object(previous_raw_event)

    new_state_object = create_state_object(
        new_raw_event, previous=previous_state_object
    )
    return new_state_object
