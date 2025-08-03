import json
import logging
import string
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, TypeAlias, TypeVar, Union, overload

import aiomqtt
from switchbot import SwitchBotAdvertisement

RawStateEvent: TypeAlias = Union[SwitchBotAdvertisement, aiomqtt.Message]
T_State = TypeVar("T_State", bound=RawStateEvent)

logger = logging.getLogger(__name__)


class MqttFormatter(string.Formatter):
    def get_field(self, field_name, args, kwargs):
        # Handle dot notation for nested access
        obj = kwargs
        for part in field_name.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return (
                    None,
                    field_name,
                )  # Return None if not found, and original field_name
        return obj, field_name


class StateObject(ABC, Generic[T_State]):
    def __init__(self, raw_event: T_State):
        self._raw_event: T_State = raw_event
        self._cached_values: Dict[str, Any] | None = None

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
        all_values = self.get_values_dict()
        formatter = MqttFormatter()

        if isinstance(template_data, dict):
            return {k: self.format(str(v)) for k, v in template_data.items()}
        else:
            return formatter.format(str(template_data), **all_values)


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


def create_state_object(raw_event: RawStateEvent) -> StateObject:
    if isinstance(raw_event, SwitchBotAdvertisement):
        return SwitchBotState(raw_event)
    elif isinstance(raw_event, aiomqtt.Message):
        return MqttState(raw_event)
    raise TypeError(f"Unsupported event type: {type(raw_event)}")
