import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from switchbot_actions.action_executor import (
    MqttPublishExecutor,
    ShellCommandExecutor,
    WebhookExecutor,
)
from switchbot_actions.config import (
    MqttPublishAction,
    ShellCommandAction,
    WebhookAction,
)
from switchbot_actions.evaluator import format_string


# --- Tests for format_string ---
def test_format_string(mock_switchbot_advertisement):
    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    template = "Temp: {temperature}, Hum: {humidity}, RSSI: {rssi}, Addr: {address}"
    result = format_string(template, state_object)
    assert result == "Temp: 29.0, Hum: 65, RSSI: -70, Addr: DE:AD:BE:EF:11:11"


# --- Tests for ShellCommandExecutor ---
@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_shell_command_executor(
    mock_create_subprocess_shell, mock_switchbot_advertisement
):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"stdout_output", b"stderr_output")
    mock_process.returncode = 0
    mock_create_subprocess_shell.return_value = mock_process

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:22:22",
        rssi=-55,
        data={
            "modelName": "WoHand",
            "data": {"isOn": True, "battery": 95},
        },
    )
    action_config = ShellCommandAction(
        type="shell_command",
        command="echo 'Bot {address} pressed'",
    )
    executor = ShellCommandExecutor(action_config)
    await executor.execute(state_object)

    mock_create_subprocess_shell.assert_called_once_with(
        format_string(action_config.command, state_object),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_process.communicate.assert_called_once()


# --- Tests for WebhookExecutor ---
@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.WebhookExecutor._send_request")
async def test_webhook_executor_post(mock_send_request, mock_switchbot_advertisement):
    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        data={"data": {"temperature": 29.0}},
    )
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
    await executor.execute(mqtt_message_json)

    mock_signal_send.assert_called_once_with(
        None,
        topic="home/actors/actor1",
        payload={"new_temp": "28.5"},
        qos=0,
        retain=False,
    )
