from datetime import timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)
from pytimeparse2 import parse
from ruamel.yaml.comments import CommentedSeq


def to_upper(v: Any) -> Any:
    if isinstance(v, str):
        return v.upper()
    return v


LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]
CaseInsensitiveLogLevel = Annotated[LogLevel, BeforeValidator(to_upper)]


class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MqttSettings(BaseConfigModel):
    host: str
    port: int = Field(1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    reconnect_interval: int = 10


class PrometheusExporterSettings(BaseConfigModel):
    enabled: bool = False
    port: int = Field(8000, ge=1, le=65535)
    target: Dict[str, Any] = Field(default_factory=dict)


class ScannerSettings(BaseConfigModel):
    cycle: int = 10
    duration: int = 3
    interface: int = 0

    @model_validator(mode="after")
    def validate_duration_less_than_cycle(self):
        if self.duration > self.cycle:
            raise ValueError(
                "scanner.duration must be less than or equal to scanner.cycle"
            )
        return self


class LoggingSettings(BaseConfigModel):
    level: CaseInsensitiveLogLevel = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loggers: Dict[str, CaseInsensitiveLogLevel] = Field(default_factory=dict)


class AutomationIf(BaseConfigModel):
    _name: str = PrivateAttr(default="")
    source: Literal["switchbot", "switchbot_timer", "mqtt", "mqtt_timer"]
    duration: Optional[float] = None
    conditions: Dict[str, Any] = Field(default_factory=dict)
    topic: Optional[str] = None
    device: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    @field_validator("duration", mode="before")
    def parse_duration_string(cls, v: Any) -> Optional[float]:
        if isinstance(v, str):
            parsed_duration = parse(v)
            if parsed_duration is None:
                raise ValueError(f"Invalid duration string: {v}")
            if isinstance(parsed_duration, timedelta):
                return parsed_duration.total_seconds()
            return parsed_duration
        return v

    @model_validator(mode="after")
    def validate_duration_for_timer_source(self):
        if self.source in ["switchbot_timer", "mqtt_timer"] and self.duration is None:
            raise ValueError(f"'duration' is required for source '{self.source}'")
        return self

    @model_validator(mode="after")
    def validate_topic_for_mqtt_source(self):
        if self.source in ["mqtt", "mqtt_timer"] and self.topic is None:
            raise ValueError(f"'topic' is required for source '{self.source}'")
        return self


class ShellCommandAction(BaseConfigModel):
    type: Literal["shell_command"]
    command: str


class WebhookAction(BaseConfigModel):
    type: Literal["webhook"]
    url: str
    method: str = "POST"
    payload: Union[str, Dict[str, Any]] = ""
    headers: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("method")
    def validate_method(cls, v: str) -> str:
        upper_v = v.upper()
        if upper_v not in ["POST", "GET"]:
            raise ValueError("method must be POST or GET")
        return upper_v


class MqttPublishAction(BaseConfigModel):
    type: Literal["mqtt_publish"]
    topic: str
    payload: Union[str, Dict[str, Any]] = ""
    qos: Literal[0, 1, 2] = 0
    retain: bool = False


class DeviceSettings(BaseConfigModel):
    address: str
    config: Dict[str, Any] = Field(default_factory=dict)


class SwitchBotCommandAction(BaseConfigModel):
    type: Literal["switchbot_command"]
    device: Optional[str] = None  # Reference to a device in the top-level devices map
    address: Optional[str] = None  # Direct address, for self-contained actions
    config: Dict[str, Any] = Field(
        default_factory=dict
    )  # Constructor arguments, for self-contained actions
    command: str
    params: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_device_or_address(self) -> "SwitchBotCommandAction":
        if not self.device and not self.address:
            raise ValueError("Either 'device' or 'address' must be specified.")
        if self.device and self.address:
            raise ValueError("'device' and 'address' cannot be used simultaneously.")
        return self


AutomationAction = Annotated[
    Union[ShellCommandAction, WebhookAction, MqttPublishAction, SwitchBotCommandAction],
    Field(discriminator="type"),
]


class AutomationRule(BaseConfigModel):
    name: Optional[str] = None
    cooldown: Optional[str] = None

    if_block: AutomationIf = Field(alias="if")
    then_block: List[AutomationAction] = Field(alias="then")

    @field_validator("then_block", mode="before")
    def validate_then_block(cls, v: Any) -> Any:
        if isinstance(v, dict):
            # Use ruamel.yaml's CommentedSeq instead of a standard list
            seq = CommentedSeq([v])
            # Transfer the line information from the original dict to the new sequence
            if hasattr(v, "lc"):
                seq.lc.line = v.lc.line  # type: ignore[attr-defined]
                seq.lc.col = v.lc.col  # type: ignore[attr-defined]
            return seq
        return v

    @model_validator(mode="after")
    def _assign_descriptive_name_to_if_block(self) -> "AutomationRule":
        if self.if_block:
            rule_name = self.name or "Unnamed Rule"
            self.if_block._name = f"{rule_name}:{self.if_block.source}"
        return self


class AppSettings(BaseConfigModel):
    config_path: str = "config.yaml"
    debug: bool = False
    devices: Dict[str, DeviceSettings] = Field(default_factory=dict)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    prometheus_exporter: PrometheusExporterSettings = Field(
        default_factory=PrometheusExporterSettings  # type: ignore[arg-type]
    )
    automations: List[AutomationRule] = Field(default_factory=list)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    mqtt: Optional[MqttSettings] = None

    @model_validator(mode="after")
    def set_default_automation_names(self) -> "AppSettings":
        for i, rule in enumerate(self.automations):
            if rule.name is None:
                rule.name = f"Unnamed Rule #{i}"
        return self

    @model_validator(mode="after")
    def resolve_device_references(self) -> "AppSettings":
        for rule in self.automations:
            for action in rule.then_block:
                if isinstance(action, SwitchBotCommandAction):
                    if action.device:
                        device_settings = self.devices.get(action.device)
                        if not device_settings:
                            raise ValueError(
                                f"Device '{action.device}' not found "
                                f"in devices section."
                            )
                        action.address = device_settings.address
                        # Device-level config is merged with action-level config,
                        # with action-level taking precedence.
                        action.config = {
                            **device_settings.config,
                            **action.config,
                        }
            if rule.if_block.device:
                device_name = rule.if_block.device
                device_settings = self.devices.get(device_name)
                if not device_settings:
                    raise ValueError(
                        f"Device '{device_name}' not found in devices section "
                        f"for if_block."
                    )
                rule.if_block.conditions["address"] = device_settings.address
        return self
