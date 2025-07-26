import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions import action_executor


# --- Tests for format_string ---
def test_format_string():
    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:11:11"
    state_object.rssi = -70
    state_object.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    template = "Temp: {temperature}, Hum: {humidity}, RSSI: {rssi}, Addr: {address}"
    result = action_executor.format_string(template, state_object)
    assert result == "Temp: 29.0, Hum: 65, RSSI: -70, Addr: DE:AD:BE:EF:11:11"


# --- Tests for execute_action ---
@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_execute_action_shell(mock_create_subprocess_shell):
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"stdout_output", b"stderr_output")
    mock_process.returncode = 0
    mock_create_subprocess_shell.return_value = mock_process

    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:22:22"
    state_object.rssi = -55
    state_object.data = {"modelName": "WoHand", "data": {"isOn": True, "battery": 95}}
    action_config = {
        "type": "shell_command",
        "command": "echo 'Bot {address} pressed'",
    }
    await action_executor.execute_action(action_config, state_object)
    mock_create_subprocess_shell.assert_called_once_with(
        "echo 'Bot DE:AD:BE:EF:22:22 pressed'",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_process.communicate.assert_called_once()


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_post_success(mock_async_client, caplog):
    caplog.set_level(logging.DEBUG)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_post = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:11:11"
    state_object.rssi = -70
    state_object.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    action_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "POST",
        "payload": {"temp": "{temperature}", "addr": "{address}"},
    }
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with(
        "http://example.com/hook", json=expected_payload, headers={}, timeout=10
    )
    assert (
        "Webhook to http://example.com/hook successful with status 200" in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_get_success(mock_async_client, caplog):
    caplog.set_level(logging.DEBUG)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_get = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.get = mock_get

    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:11:11"
    state_object.rssi = -70
    state_object.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    action_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "GET",
        "payload": {"temp": "{temperature}", "addr": "{address}"},
    }
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_get.assert_called_once_with(
        "http://example.com/hook", params=expected_payload, headers={}, timeout=10
    )
    assert (
        "Webhook to http://example.com/hook successful with status 200" in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_post_failure_400(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request: Invalid payload"
    mock_post = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:11:11"
    state_object.rssi = -70
    state_object.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    action_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "POST",
        "payload": {"temp": "{temperature}", "addr": "{address}"},
    }
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with(
        "http://example.com/hook", json=expected_payload, headers={}, timeout=10
    )
    assert (
        "Webhook to http://example.com/hook failed with status 400. "
        "Response: Bad Request: Invalid payload" in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_get_failure_500(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error: Something went wrong on the server."
    mock_get = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.get = mock_get

    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:11:11"
    state_object.rssi = -70
    state_object.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    action_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "GET",
        "payload": {"temp": "{temperature}", "addr": "{address}"},
    }
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_get.assert_called_once_with(
        "http://example.com/hook", params=expected_payload, headers={}, timeout=10
    )
    assert (
        "Webhook to http://example.com/hook failed with status 500. "
        "Response: Internal Server Error: Something went wrong on the server."
        in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_unsupported_method(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_client = AsyncMock()
    mock_async_client.return_value.__aenter__.return_value = mock_client

    state_object = MagicMock()
    action_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "PUT",  # Unsupported method
        "payload": {},
    }
    await action_executor.execute_action(action_config, state_object)
    mock_client.post.assert_not_called()
    mock_client.get.assert_not_called()
    assert "Unsupported HTTP method for webhook: PUT" in caplog.text
