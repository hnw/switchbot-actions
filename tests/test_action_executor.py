import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_actions import action_executor
from switchbot_actions.config import (
    MqttPublishAction,
    ShellCommandAction,
    WebhookAction,
)


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
    result = action_executor.format_string(template, state_object)
    assert result == "Temp: 29.0, Hum: 65, RSSI: -70, Addr: DE:AD:BE:EF:11:11"


# --- Tests for execute_action ---
@pytest.mark.asyncio
@patch("asyncio.create_subprocess_shell")
async def test_execute_action_shell(
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
    await action_executor.execute_action(action_config, state_object)
    mock_create_subprocess_shell.assert_called_once_with(
        action_executor.format_string(action_config.command, state_object),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mock_process.communicate.assert_called_once()


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_post_success(
    mock_async_client, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.DEBUG)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_post = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="POST",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with(
        action_executor.format_string(action_config.url, state_object),
        json=expected_payload,
        headers={},
        timeout=10,
    )
    assert (
        "Webhook to http://example.com/hook successful with status 200" in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_get(
    mock_async_client, mock_switchbot_advertisement
):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_get = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.get = mock_get

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="GET",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
    await action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_get.assert_called_once_with(
        action_executor.format_string(action_config.url, state_object),
        params=expected_payload,
        headers={},
        timeout=10,
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_execute_action_webhook_get_success(
    mock_async_client, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.DEBUG)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_get = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.get = mock_get

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="GET",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
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
async def test_execute_action_webhook_post_failure_400(
    mock_async_client, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request: Invalid payload"
    mock_post = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.post = mock_post

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="POST",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
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
async def test_execute_action_webhook_get_failure_500(
    mock_async_client, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error: Something went wrong on the server."
    mock_get = AsyncMock(return_value=mock_response)
    mock_async_client.return_value.__aenter__.return_value.get = mock_get

    state_object = mock_switchbot_advertisement(
        address="DE:AD:BE:EF:11:11",
        rssi=-70,
        data={
            "modelName": "WoSensorTH",
            "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
        },
    )
    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="GET",
        payload={"temp": "{temperature}", "addr": "{address}"},
    )
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
async def test_execute_action_webhook_unsupported_method(
    mock_async_client, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_client = AsyncMock()
    mock_async_client.return_value.__aenter__.return_value = mock_client

    state_object = mock_switchbot_advertisement()

    # Create a dummy action config that is not a valid AutomationAction subclass
    # to test the unsupported method logging.
    class DummyAction:
        type = "webhook"
        url = "http://example.com/hook"
        method = "PUT"
        payload = {}
        headers = {}

    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="GET",  # Use a valid method for instantiation
        payload={},
    )
    # Temporarily change the method to an unsupported one for testing
    with patch.object(action_config, "method", "PUT"):
        await action_executor.execute_action(action_config, state_object)
    mock_client.post.assert_not_called()
    mock_client.get.assert_not_called()
    assert "Unsupported HTTP method for webhook: PUT" in caplog.text


@pytest.mark.asyncio
async def test_execute_action_unknown_type(caplog, mock_switchbot_advertisement):
    caplog.set_level(logging.WARNING)
    state_object = mock_switchbot_advertisement()
    # Create a mock object that is not an instance of any AutomationAction subclass
    # to test the unknown type logging.
    mock_action_config = MagicMock()
    mock_action_config.type = "unknown_action"

    await action_executor.execute_action(mock_action_config, state_object)
    assert "Unknown trigger type: unknown_action" in caplog.text


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor.publish_mqtt_message_request.send")
async def test_execute_action_mqtt_publish(mock_signal_send, mqtt_message_json):
    """Test that mqtt_publish action sends the correct signal."""
    state_object = mqtt_message_json
    action_config = MqttPublishAction(
        type="mqtt_publish",
        topic="home/actors/actor1",
        payload={"new_temp": "{temperature}"},
        qos=1,
        retain=True,
    )

    await action_executor.execute_action(action_config, state_object)

    mock_signal_send.assert_called_once_with(
        None,
        topic="home/actors/actor1",
        payload='{"new_temp": "28.5"}',
        qos=1,
        retain=True,
    )
