import re
from datetime import timedelta
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
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


class DeviceSettings(BaseConfigModel):
    address: str
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("address")
    @classmethod
    def validate_and_normalize_address(cls, v: str) -> str:
        """
        Validates that the address is a valid MAC address or UUID,
        and normalizes it to a canonical format.
        """
        # Regex for MAC addresses (colon/hyphen separated, case-insensitive)
        mac_regex = re.compile(r"^([0-9a-f]{2}[:-]){5}([0-9a-f]{2})$", re.IGNORECASE)
        # Regular expression for UUIDs (case-insensitive)
        uuid_regex = re.compile(
            r"^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$", re.IGNORECASE
        )

        if mac_regex.match(v):
            # For MAC addresses, convert to uppercase and unify hyphens to colons
            return v.upper().replace("-", ":")

        if uuid_regex.match(v):
            # For UUIDs, convert to uppercase
            return v.upper()

        raise ValueError(
            f"Address '{v}' is not a valid MAC address "
            "(e.g., '11:22:33:AA:BB:CC') or UUID (for macOS)."
        )


class MqttSettings(BaseConfigModel):
    enabled: bool = False
    host: str = "localhost"
    port: int = Field(1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    reconnect_interval: float = 10.0


class PrometheusExporterSettings(BaseConfigModel):
    enabled: bool = False
    port: int = Field(8000, ge=1, le=65535)
    target: Dict[str, Any] = Field(default_factory=dict)
    devices: Dict[str, DeviceSettings] = Field(default_factory=dict)


class ScannerSettings(BaseConfigModel):
    enabled: bool = True
    duration: int = 3
    wait: int = 1
    interface: int = 0


class LoggingSettings(BaseConfigModel):
    level: CaseInsensitiveLogLevel = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loggers: Dict[str, CaseInsensitiveLogLevel] = Field(default_factory=dict)


class AutomationIf(BaseConfigModel):
    """
    Defines the trigger conditions for an automation rule.

    The behavior of the trigger (immediate vs. time-based) is determined
    by the presence of the 'duration' field.

    - If 'duration' is absent, the trigger is immediate, firing as soon as
      the specified 'source' event occurs and 'conditions' are met.
    - If 'duration' is present, the trigger is time-based. It fires only if
      the 'source' event and 'conditions' remain true for the specified
      duration.

    The 'source' field's sole responsibility is to define the origin of the
    event (e.g., 'switchbot' for BLE advertisements, 'mqtt' for MQTT messages),
    not its timing behavior.
    """

    _name: str = PrivateAttr(default="")
    source: Literal["switchbot", "mqtt"]
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
    def validate_topic_for_mqtt_source(self):
        if self.source == "mqtt" and self.topic is None:
            raise ValueError(f"'topic' is required for source '{self.source}'")
        return self


class ShellCommandAction(BaseConfigModel):
    type: Literal["shell_command"]
    command: List[str]


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


class LogAction(BaseConfigModel):
    type: Literal["log"]
    message: str
    level: CaseInsensitiveLogLevel = "INFO"


AutomationAction = Annotated[
    Union[
        ShellCommandAction,
        WebhookAction,
        MqttPublishAction,
        SwitchBotCommandAction,
        LogAction,
    ],
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


class AutomationSettings(BaseConfigModel):
    rules: List[AutomationRule] = Field(default_factory=list)
    devices: Dict[str, DeviceSettings] = Field(default_factory=dict)

    @field_validator("devices")
    @classmethod
    def validate_device_alias_names(
        cls, v: Dict[str, DeviceSettings]
    ) -> Dict[str, DeviceSettings]:
        """
        Validates that device alias names do not contain characters that conflict
        with the string formatter syntax (e.g., '.', '[', ']').
        """
        # Forbidden characters that conflict with formatter syntax
        FORBIDDEN_CHARS = [".", "[", "]"]

        for alias in v.keys():
            if any(char in alias for char in FORBIDDEN_CHARS):
                raise ValueError(
                    f"Device alias '{alias}' contains invalid characters. "
                    f"Dots (.) and square brackets ([]) are not allowed."
                )
        return v


class AppSettings(BaseConfigModel):
    config_path: str = "config.yaml"
    debug: bool = False
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    prometheus: PrometheusExporterSettings = Field(
        default_factory=PrometheusExporterSettings  # pyright:ignore[reportArgumentType]
    )
    automations: AutomationSettings = Field(default_factory=AutomationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    mqtt: MqttSettings = Field(
        default_factory=MqttSettings  # pyright:ignore[reportArgumentType]
    )

    @model_validator(mode="before")
    @classmethod
    def transform_automation_settings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            automations_data = {}
            if "automations" in data:
                automations_data["rules"] = data.pop("automations")
                if "devices" in data:
                    automations_data["devices"] = data.pop("devices")
                data["automations"] = automations_data
            if "prometheus" in data and "devices" in data:
                data["prometheus"]["devices"] = data.pop("devices")

        return data

    @model_validator(mode="after")
    def set_default_automation_names(self) -> "AppSettings":
        for i, rule in enumerate(self.automations.rules):
            if rule.name is None:
                rule.name = f"Automation #{i}"
            if rule.if_block:
                rule.if_block._name = rule.name
        return self

    @model_validator(mode="after")
    def resolve_device_references(self) -> "AppSettings":
        for rule in self.automations.rules:
            for action in rule.then_block:
                if isinstance(action, SwitchBotCommandAction):
                    if action.device:
                        device_settings = self.automations.devices.get(action.device)
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
                device_settings = self.automations.devices.get(device_name)
                if not device_settings:
                    raise ValueError(
                        f"Device '{device_name}' not found in devices section "
                        f"for if_block."
                    )
                rule.if_block.conditions["address"] = device_settings.address
        return self

    @model_validator(mode="after")
    def validate_cross_device_condition_aliases(self) -> "AppSettings":
        """
        Validates that any device alias used in a cross-device condition
        (e.g., 'alias.attribute') is defined in the top-level 'devices' section.
        """
        if not self.automations or not self.automations.devices:
            # No check needed if there is no devices section
            return self

        defined_aliases = self.automations.devices.keys()
        errors = []

        for i, rule in enumerate(self.automations.rules):
            # Ensure rule.if_block and rule.if_block.conditions exist before iterating
            if not rule.if_block or not rule.if_block.conditions:
                continue

            for condition_key in rule.if_block.conditions.keys():
                if "." not in condition_key:
                    continue  # Skip if not a cross-device condition

                alias, attribute = condition_key.split(".", 1)

                if alias == "previous":
                    # 'previous' is a special keyword, so skip
                    continue

                if alias not in defined_aliases:
                    msg = (
                        f"In automation rule '{rule.name}', the condition "
                        f"'{condition_key}' refers to a device alias '{alias}' "
                        "that is not defined in the top-level 'devices' section."
                    )
                    exc = ValueError(msg)

                    errors.append(
                        {
                            "type": "value_error",
                            "loc": (
                                "automations",
                                "rules",
                                i,
                                "if",
                                "conditions",
                                condition_key,
                            ),
                            "msg": msg,
                            "ctx": {"error": exc},
                        }
                    )

        if errors:
            raise ValidationError.from_exception_data(
                title=self.__class__.__name__, line_errors=errors
            )

        return self
