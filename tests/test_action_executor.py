import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from switchbot import Switchbot, SwitchbotModel

from switchbot_actions.action_executor import (
    LogExecutor,
    MqttPublishExecutor,
    ShellCommandExecutor,
    SwitchBotCommandExecutor,
    WebhookExecutor,
    create_action_executor,
)
from switchbot_actions.config import (
    LogAction,
    MqttPublishAction,
    ShellCommandAction,
    SwitchBotCommandAction,
    WebhookAction,
)
from switchbot_actions.signals import action_executed
from switchbot_actions.state import create_state_object
from switchbot_actions.store import StateStore


# --- Tests for LogExecutor ---
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "log_level, expected_log_method",
    [
        ("DEBUG", "debug"),
        ("INFO", "info"),
        ("WARNING", "warning"),
        ("ERROR", "error"),
        ("CRITICAL", "critical"),
    ],
)
async def test_log_executor_logs_message_at_correct_level(
    log_level, expected_log_method, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.DEBUG)  # Capture all levels

    raw_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        data={"data": {"temperature": 29.0}},
    )
    state_object = create_state_object(raw_state)

    message_template = "Current temperature is {temperature} at {address}"
    action_config = LogAction(type="log", message=message_template, level=log_level)
    executor = LogExecutor(action_config)
    await executor.execute(state_object)

    expected_message = "Current temperature is 29.0 at DE:AD:BE:EF:11:11"

    # Check if the log record exists and has the correct level and message
    found = False
    for record in caplog.records:
        if (
            record.name == "switchbot_actions.automation"
            and record.msg == expected_message
        ):
            assert record.levelname == log_level
            found = True
            break
    assert found, f"Log message '{expected_message}' not found with level '{log_level}'"


# --- Tests for ShellCommandExecutor ---
@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_shell_command_executor(
    mock_create_subprocess_exec, mock_switchbot_advertisement
):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"stdout_output", b"stderr_output")
    mock_process.returncode = 0
    mock_create_subprocess_exec.return_value = mock_process

    raw_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:22:22",
        rssi=-55,
        data={
            "modelName": "WoHand",
            "data": {"isOn": True, "battery": 95},
        },
    )
    state_object = create_state_object(raw_state)
    action_config = ShellCommandAction(
        type="shell_command",
        command=["echo", "Bot {address} pressed"],
    )
    executor = ShellCommandExecutor(action_config)
    await executor.execute(state_object)

    mock_create_subprocess_exec.assert_called_once_with(
        "echo",
        "Bot DE:AD:BE:EF:22:22 pressed",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_process.communicate.assert_called_once()


@pytest.mark.asyncio
@patch("asyncio.create_subprocess_exec")
async def test_shell_command_executor_file_not_found_error(
    mock_create_subprocess_exec, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)

    mock_create_subprocess_exec.side_effect = FileNotFoundError

    raw_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:33:33",
        data={"modelName": "Meter", "data": {"temperature": 25.0}},
    )
    state_object = create_state_object(raw_state)

    non_existent_command = "/a/b/c/non-existent-command"
    action_config = ShellCommandAction(
        type="shell_command",
        command=[non_existent_command, "arg1", "arg2"],
    )
    executor = ShellCommandExecutor(action_config)
    await executor.execute(state_object)

    mock_create_subprocess_exec.assert_called_once_with(
        non_existent_command,
        "arg1",
        "arg2",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert (
        f"Shell command not found: '{non_existent_command}'. "
        "Please ensure the command is installed and in your system's PATH."
        in caplog.text
    )


# --- Tests for WebhookExecutor ---
@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.WebhookExecutor._send_request")
async def test_webhook_executor_post(mock_send_request, mock_switchbot_advertisement):
    raw_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        data={"data": {"temperature": 29.0}},
    )
    state_object = create_state_object(raw_state)
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="POST",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
    executor = WebhookExecutor(action_config)
    await executor.execute(state_object)

    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_send_request.assert_called_once_with(
        "http://example.com/hook", "POST", expected_payload, {}
    )


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.time.perf_counter")
@patch.object(action_executed, "send")
@patch("switchbot_actions.action_executor.WebhookExecutor._send_request")
async def test_measure_execution_time_decorator_sends_signal_and_logs(
    mock_send_request,
    mock_action_executed_send,
    mock_perf_counter,
    caplog,
    mock_switchbot_advertisement,
):
    caplog.set_level(logging.DEBUG)

    # duration = 0.1234 sec => 123.4ms
    mock_perf_counter.side_effect = [1.0, 1.1234]

    raw_state = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        data={"data": {"temperature": 29.0}},
    )
    state_object = create_state_object(raw_state)

    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="POST",
        payload={"temp": "{temperature}"},
    )
    executor = WebhookExecutor(action_config)
    await executor.execute(state_object)

    assert "Action 'webhook' finished (took 123.4ms)" in caplog.text
    mock_action_executed_send.assert_called_once()
    sender = mock_action_executed_send.call_args.args[0]
    kwargs = mock_action_executed_send.call_args.kwargs
    assert sender is executor
    assert kwargs["action_type"] == "webhook"
    assert kwargs["duration"] == pytest.approx(0.1234)


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_webhook_send_request_post_success(mock_async_client, caplog):
    caplog.set_level(logging.DEBUG)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_async_client.return_value.__aenter__.return_value.post.return_value = (
        mock_response
    )

    executor = WebhookExecutor(WebhookAction(type="webhook", url="http://test.com"))
    await executor._send_request(
        "http://test.com", "POST", {"key": "value"}, {"h": "v"}
    )

    assert "Webhook to http://test.com successful" in caplog.text


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_webhook_send_request_get_failure(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.text = "Server Error"
    mock_async_client.return_value.__aenter__.return_value.get.return_value = (
        mock_response
    )

    executor = WebhookExecutor(WebhookAction(type="webhook", url="http://test.com"))
    await executor._send_request("http://test.com", "GET", {"p": "v"}, {"h": "v"})

    assert "Webhook to http://test.com failed with status 500" in caplog.text


@pytest.mark.asyncio
async def test_webhook_send_request_unsupported_method(caplog):
    caplog.set_level(logging.ERROR)
    executor = WebhookExecutor(WebhookAction(type="webhook", url="http://test.com"))
    await executor._send_request("http://test.com", "PUT", {}, {})
    assert "Unsupported HTTP method for webhook: PUT" in caplog.text


# --- Tests for MqttPublishExecutor ---
@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.publish_mqtt_message_request.send")
async def test_mqtt_publish_executor(mock_signal_send, mqtt_message_json):
    action_config = MqttPublishAction(
        type="mqtt_publish",
        topic="home/actors/actor1",
        payload={"new_temp": "{temperature}"},
    )
    executor = MqttPublishExecutor(action_config)
    state_object = create_state_object(mqtt_message_json)
    await executor.execute(state_object)

    mock_signal_send.assert_called_once_with(
        None,
        topic="home/actors/actor1",
        payload={"new_temp": "28.5"},
        qos=0,
        retain=False,
    )


# --- Tests for SwitchBotCommandExecutor ---
@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.create_switchbot_device")
async def test_switchbot_command_executor_success(
    mock_create_device, mock_switchbot_advertisement
):
    mock_device_instance = AsyncMock(spec=Switchbot)
    mock_device_instance.update_from_advertisement = MagicMock()

    mock_create_device.return_value = mock_device_instance

    address = "DE:AD:BE:EF:33:33"
    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": SwitchbotModel.BOT, "data": {"isOn": True}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = advertisement

    action_config = SwitchBotCommandAction(
        type="switchbot_command", address=address, command="turn_on"
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    state_store.get.assert_called_once_with(address)

    mock_create_device.assert_called_once_with(advertisement)
    mock_device_instance.update_from_advertisement.assert_called_once_with(
        advertisement
    )
    mock_device_instance.turn_on.assert_awaited_once()


@pytest.mark.asyncio
async def test_switchbot_command_executor_device_not_found(
    caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    address = "DE:AD:BE:EF:44:44"
    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": SwitchbotModel.BOT, "data": {"isOn": True}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = None

    action_config = SwitchBotCommandAction(
        type="switchbot_command", address=address, command="turn_on"
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    assert f"Device with address {address} not found" in caplog.text


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.create_switchbot_device")
async def test_switchbot_command_executor_unsupported_device(
    mock_create_device, mock_switchbot_advertisement, caplog
):
    """
    Test that an informative error is logged when the device model
    is not supported for direct control.
    """
    caplog.set_level(logging.ERROR)

    mock_create_device.return_value = None

    address = "DE:AD:BE:EF:88:88"
    unsupported_model = "WoUnsupportedDevice"

    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": unsupported_model, "data": {}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = advertisement

    action_config = SwitchBotCommandAction(
        type="switchbot_command",
        address=address,
        command="press",
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    assert f"Failed to execute 'switchbot_command' on '{address}'" in caplog.text
    assert (
        f"Direct control for model '{unsupported_model}' is not implemented"
        in caplog.text
    )
    assert (
        "To request support, please open an issue on GitHub with the model name."
        in caplog.text
    )


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.create_switchbot_device")
async def test_switchbot_command_executor_invalid_command(
    mock_create_device, mock_switchbot_advertisement, caplog
):
    caplog.set_level(logging.ERROR)

    mock_device_instance = AsyncMock(spec=Switchbot)
    mock_device_instance.update_from_advertisement = MagicMock()
    del mock_device_instance.invalid_command

    mock_create_device.return_value = mock_device_instance

    address = "DE:AD:BE:EF:55:55"
    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": SwitchbotModel.BOT, "data": {"isOn": True}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = advertisement

    action_config = SwitchBotCommandAction(
        type="switchbot_command", address=address, command="invalid_command"
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    assert "Invalid command 'invalid_command'" in caplog.text


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.create_switchbot_device")
async def test_switchbot_command_executor_invalid_arguments(
    mock_create_device, mock_switchbot_advertisement, caplog
):
    caplog.set_level(logging.ERROR)

    mock_device_instance = AsyncMock(spec=Switchbot)
    mock_device_instance.update_from_advertisement = MagicMock()
    mock_device_instance.turn_on.side_effect = TypeError("Invalid argument type")

    mock_create_device.return_value = mock_device_instance

    address = "DE:AD:BE:EF:66:66"
    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": SwitchbotModel.BOT, "data": {"isOn": True}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = advertisement

    action_config = SwitchBotCommandAction(
        type="switchbot_command",
        address=address,
        command="turn_on",
        params={"unexpected_arg": True},
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    assert "Invalid arguments for command 'turn_on'" in caplog.text


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.create_switchbot_device")
async def test_switchbot_command_executor_execution_exception(
    mock_create_device, mock_switchbot_advertisement, caplog
):
    caplog.set_level(logging.ERROR)

    mock_device_instance = AsyncMock(spec=Switchbot)
    mock_device_instance.update_from_advertisement = MagicMock()
    mock_device_instance.press.side_effect = Exception("Device communication failed")

    mock_create_device.return_value = mock_device_instance

    address = "DE:AD:BE:EF:77:77"
    advertisement = mock_switchbot_advertisement(
        address=address,
        data={"modelName": SwitchbotModel.BOT, "data": {"isOn": True}},
    )
    state_object = create_state_object(advertisement)

    state_store = MagicMock(spec=StateStore)
    state_store.get.return_value = advertisement

    action_config = SwitchBotCommandAction(
        type="switchbot_command",
        address=address,
        command="press",
    )
    executor = SwitchBotCommandExecutor(action_config, state_store)
    await executor.execute(state_object)

    assert (
        f"Failed to execute command on {address}: Device communication failed"
        in caplog.text
    )


# --- Tests for create_action_executor ---
def test_create_action_executor_raises_error_for_unknown_type():
    """Test that the factory function raises a ValueError for an unknown action type."""
    mock_action = MagicMock()
    mock_action.type = "unknown"
    with pytest.raises(ValueError, match="Unknown action type: unknown"):
        create_action_executor(mock_action, MagicMock(spec=StateStore))
