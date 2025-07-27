from datetime import timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pytimeparse2 import parse


class MqttSettings(BaseModel):
    host: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    reconnect_interval: int = 10


class PrometheusExporterSettings(BaseModel):
    enabled: bool = False
    port: int = 8000
    target: Dict[str, Any] = Field(default_factory=dict)


class ScannerSettings(BaseModel):
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


class LoggingSettings(BaseModel):
    level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"] = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loggers: Dict[str, str] = Field(default_factory=dict)


class AutomationIf(BaseModel):
    source: str
    duration: Optional[float] = None
    device: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    topic: Optional[str] = None

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


class ShellCommandAction(BaseModel):
    type: Literal["shell_command"]
    command: str


class WebhookAction(BaseModel):
    type: Literal["webhook"]
    url: str
    method: Literal["POST", "GET"] = "POST"  # TODO：.upper()
    payload: Union[str, Dict[str, Any]] = ""
    headers: Dict[str, Any] = Field(default_factory=dict)


class MqttPublishAction(BaseModel):
    type: Literal["mqtt_publish"]
    topic: str
    payload: Union[str, Dict[str, Any]] = ""
    qos: int = 0
    retain: bool = False


AutomationAction = Annotated[
    Union[ShellCommandAction, WebhookAction, MqttPublishAction],
    Field(discriminator="type"),
]


class AutomationRule(BaseModel):
    name: Optional[str] = None
    cooldown: Optional[str] = None

    if_block: AutomationIf = Field(alias="if")
    then_block: List[AutomationAction] = Field(alias="then")

    @field_validator("then_block", mode="before")
    def validate_then_block(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return [v]  # Convert single dict to a list containing that dict
        return v


class AppSettings(BaseModel):
    config_path: str = "config.yaml"
    debug: bool = False
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    prometheus_exporter: PrometheusExporterSettings = Field(
        default_factory=PrometheusExporterSettings
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
