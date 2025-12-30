import asyncio
import logging
import time
from abc import ABC, abstractmethod
from functools import wraps
from typing import Generic, TypeVar

import httpx
from switchbot import SwitchBotAdvertisement

from .config import (
    AutomationAction,
    LogAction,
    MqttPublishAction,
    ShellCommandAction,
    SwitchBotCommandAction,
    WebhookAction,
)
from .signals import action_executed, publish_mqtt_message_request
from .state import StateObject
from .store import StateStore
from .switchbot_factory import create_switchbot_device

T_Action = TypeVar("T_Action", bound=AutomationAction)

logger = logging.getLogger("switchbot_actions.automation")


def measure_execution_time(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(self, *args, **kwargs)
        finally:
            duration = time.perf_counter() - start
            action_type = self._action_config.type

            logger.debug(
                f"Action '{action_type}' finished (took {duration * 1000.0:.1f}ms)"
            )
            action_executed.send(self, action_type=action_type, duration=duration)

    return wrapper


class ActionExecutor(ABC, Generic[T_Action]):
    """Abstract base class for action executors."""

    def __init__(self, action: T_Action):
        self._action_config: T_Action = action

    @abstractmethod
    async def execute(self, state: StateObject) -> None:
        """Executes the action."""
        pass


class ShellCommandExecutor(ActionExecutor):
    """Executes a shell command."""

    @measure_execution_time
    async def execute(self, state: StateObject) -> None:
        command_list = [state.format(arg) for arg in self._action_config.command]
        logger.debug(f"Executing command: {command_list}")
        try:
            process = await asyncio.create_subprocess_exec(
                *command_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error(
                f"Shell command not found: '{command_list[0]}'. "
                "Please ensure the command is installed and in your system's PATH."
            )
            return
        stdout, stderr = await process.communicate()
        if stdout:
            logger.debug(f"Shell command stdout: {stdout.decode().strip()}")
        if stderr:
            logger.error(f"Shell command stderr: {stderr.decode().strip()}")
        if process.returncode != 0:
            logger.error(f"Shell command failed with exit code {process.returncode}")


class WebhookExecutor(ActionExecutor):
    """Sends a webhook."""

    @measure_execution_time
    async def execute(self, state: StateObject) -> None:
        url = state.format(self._action_config.url)
        method = self._action_config.method
        payload = state.format(self._action_config.payload)
        headers = state.format(self._action_config.headers)

        message = f"Sending webhook: {method} {url}. Headers: {headers}."
        if payload:
            message += f"Payload: {payload}."

        logger.debug(message)

        await self._send_request(url, method, payload, headers)

    async def _send_request(
        self, url: str, method: str, payload: dict | str, headers: dict
    ) -> None:
        try:
            async with httpx.AsyncClient() as client:
                if method == "POST":
                    response = await client.post(
                        url, json=payload, headers=headers, timeout=10
                    )
                elif method == "GET":
                    response = await client.get(
                        url, params=payload, headers=headers, timeout=10
                    )
                else:
                    logger.error(f"Unsupported HTTP method for webhook: {method}")
                    return

                if 200 <= response.status_code < 300:
                    logger.debug(
                        f"Webhook to {url} successful with status "
                        f"{response.status_code}"
                    )
                else:
                    response_body_preview = (
                        response.text[:200] if response.text else "(empty)"
                    )
                    logger.error(
                        f"Webhook to {url} failed with status {response.status_code}. "
                        f"Response: {response_body_preview}"
                    )
        except httpx.RequestError as e:
            logger.error(f"Webhook failed: {e}")


class MqttPublishExecutor(ActionExecutor):
    """Publishes an MQTT message."""

    async def execute(self, state: StateObject) -> None:
        topic = state.format(self._action_config.topic)
        qos = self._action_config.qos
        retain = self._action_config.retain

        payload = state.format(self._action_config.payload)

        logger.debug(
            f"Publishing MQTT message to topic '{topic}' with payload '{payload}' "
            f"(qos={qos}, retain={retain})"
        )
        publish_mqtt_message_request.send(
            None, topic=topic, payload=payload, qos=qos, retain=retain
        )


class SwitchBotCommandExecutor(ActionExecutor[SwitchBotCommandAction]):
    def __init__(self, action: SwitchBotCommandAction, state_store: StateStore):
        super().__init__(action)
        self._state_store = state_store

    @measure_execution_time
    async def execute(self, state: StateObject) -> None:
        # The address should be resolved by Pydantic validation before execution.
        address = self._action_config.address
        if not address:
            logger.error(
                "SwitchBotCommandAction is missing a target device address. "
                "This indicates a problem with configuration validation."
            )
            return

        command = self._action_config.command
        constructor_args = self._action_config.config
        method_args = self._action_config.params

        advertisement = await self._state_store.get(address)
        if not advertisement:
            logger.error(f"Device with address {address} not found in StateStore.")
            return
        if not isinstance(advertisement, SwitchBotAdvertisement):
            logger.error(
                f"Retrieved state for {address} is not a SwitchBotAdvertisement. "
                f"Type: {type(advertisement).__name__}. Skipping command execution."
            )
            return

        device = create_switchbot_device(advertisement, **constructor_args)
        if not device:
            model_name = advertisement.data.get("modelName", "Unknown")
            logger.error(
                f"Failed to execute 'switchbot_command' on '{address}': "
                f"Direct control for model '{model_name}' is not implemented. "
                f"To request support, please open an issue on GitHub "
                f"with the model name."
            )
            return
        device.update_from_advertisement(advertisement)

        try:
            logger.debug(
                f"Executing command '{command}' on device {address} "
                f"with params {method_args}"
            )
            func = getattr(device, command)
            await func(**method_args)
        except AttributeError:
            logger.error(
                f"Invalid command '{command}' for device {address}. "
                "Please check your configuration."
            )
        except TypeError as e:
            logger.error(
                f"Invalid arguments for command '{command}' on device {address}. "
                f"Error: {e}. Please check your configuration."
            )
        except Exception as e:
            logger.error(f"Failed to execute command on {address}: {e}")


class LogExecutor(ActionExecutor[LogAction]):
    """Logs a message to the console."""

    def __init__(self, action: LogAction):
        super().__init__(action)

    async def execute(self, state: StateObject) -> None:
        message = state.format(self._action_config.message)
        level = self._action_config.level.lower()
        log_method = getattr(logger, level, None)
        if log_method:
            log_method(message)
        else:
            # This case should ideally be caught by Pydantic validation,
            # but as a fallback, log at info level.
            logger.info(
                f"Unknown log level '{self._action_config.level}'. "
                f"Logging as INFO: {message}"
            )


def create_action_executor(
    action: AutomationAction, state_store: StateStore
) -> ActionExecutor:
    if isinstance(action, ShellCommandAction):
        return ShellCommandExecutor(action)
    elif isinstance(action, WebhookAction):
        return WebhookExecutor(action)
    elif isinstance(action, MqttPublishAction):
        return MqttPublishExecutor(action)
    elif isinstance(action, SwitchBotCommandAction):
        return SwitchBotCommandExecutor(action, state_store)
    elif isinstance(action, LogAction):
        return LogExecutor(action)
    else:
        raise ValueError(f"Unknown action type: {action.type}")
