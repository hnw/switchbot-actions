import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_post_success(
    mock_send_webhook_request, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.DEBUG)
    mock_send_webhook_request.return_value = None  # Mock the async call

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
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "POST", expected_payload, {}
    )
    # The logging for success/failure is now inside _send_webhook_request,
    # so we don't assert it here directly from execute_action's perspective.


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_get(
    mock_send_webhook_request, mock_switchbot_advertisement
):
    mock_send_webhook_request.return_value = None

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
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "GET", expected_payload, {}
    )


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_get_success(
    mock_send_webhook_request, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.DEBUG)
    mock_send_webhook_request.return_value = None

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
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "GET", expected_payload, {}
    )
    # The logging for success/failure is now inside _send_webhook_request,
    # so we don't assert it here directly from execute_action's perspective.


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_post_failure_400(
    mock_send_webhook_request, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_send_webhook_request.return_value = None

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
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "POST", expected_payload, {}
    )
    # The logging for success/failure is now inside _send_webhook_request,
    # so we don't assert it here directly from execute_action's perspective.


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_get_failure_500(
    mock_send_webhook_request, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_send_webhook_request.return_value = None

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
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "GET", expected_payload, {}
    )
    # The logging for success/failure is now inside _send_webhook_request,
    # so we don't assert it here directly from execute_action's perspective.


@pytest.mark.asyncio
@patch("switchbot_actions.action_executor._send_webhook_request")
async def test_execute_action_webhook_unsupported_method(
    mock_send_webhook_request, caplog, mock_switchbot_advertisement
):
    caplog.set_level(logging.ERROR)
    mock_send_webhook_request.return_value = None

    state_object = mock_switchbot_advertisement()

    action_config = WebhookAction(
        type="webhook",
        url="http://example.com/hook",
        method="POST",  # Use a valid method for instantiation
        payload={},
    )
    # Temporarily change the method to an unsupported one for testing
    with patch.object(action_config, "method", "PUT"):
        await action_executor.execute_action(action_config, state_object)
    mock_send_webhook_request.assert_called_once_with(
        "http://example.com/hook", "PUT", {}, {}
    )
    # The logging for unsupported method is now inside _send_webhook_request,
    # so we don't assert it here directly from execute_action's perspective.


# --- Tests for _send_webhook_request ---
@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_post_success(mock_async_client, caplog):
    caplog.set_level(logging.DEBUG)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_async_client.return_value.__aenter__.return_value.post.return_value = (
        mock_response
    )

    url = "http://test.com/post"
    method = "POST"
    payload = {"key": "value"}
    headers = {"Content-Type": "application/json"}

    await action_executor._send_webhook_request(url, method, payload, headers)

    mock_async_client.return_value.__aenter__.return_value.post.assert_called_once_with(
        url, json=payload, headers=headers, timeout=10
    )
    assert f"Webhook to {url} successful with status 200" in caplog.text


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_get_success(mock_async_client, caplog):
    caplog.set_level(logging.DEBUG)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "OK"
    mock_async_client.return_value.__aenter__.return_value.get.return_value = (
        mock_response
    )

    url = "http://test.com/get"
    method = "GET"
    payload = {"param": "value"}
    headers = {"Accept": "application/json"}

    await action_executor._send_webhook_request(url, method, payload, headers)

    mock_async_client.return_value.__aenter__.return_value.get.assert_called_once_with(
        url, params=payload, headers=headers, timeout=10
    )
    assert f"Webhook to {url} successful with status 200" in caplog.text


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_post_failure(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_async_client.return_value.__aenter__.return_value.post.return_value = (
        mock_response
    )

    url = "http://test.com/post_fail"
    method = "POST"
    payload = {"key": "value"}
    headers = {}

    await action_executor._send_webhook_request(url, method, payload, headers)

    assert (
        f"Webhook to {url} failed with status 400. Response: Bad Request" in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_get_failure(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_async_client.return_value.__aenter__.return_value.get.return_value = (
        mock_response
    )

    url = "http://test.com/get_fail"
    method = "GET"
    payload = {"param": "value"}
    headers = {}

    await action_executor._send_webhook_request(url, method, payload, headers)

    assert (
        f"Webhook to {url} failed with status 500. Response: Internal Server Error"
        in caplog.text
    )


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_request_error(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)
    mock_async_client.return_value.__aenter__.return_value.post.side_effect = (
        httpx.RequestError(
            "Network error", request=httpx.Request("POST", "http://test.com")
        )
    )

    url = "http://test.com/error"
    method = "POST"
    payload = {"key": "value"}
    headers = {}

    await action_executor._send_webhook_request(url, method, payload, headers)

    assert "Webhook failed: Network error" in caplog.text


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_send_webhook_request_unsupported_method(mock_async_client, caplog):
    caplog.set_level(logging.ERROR)

    url = "http://test.com/unsupported"
    method = "PUT"  # Unsupported method
    payload = {"key": "value"}
    headers = {}

    await action_executor._send_webhook_request(url, method, payload, headers)

    mock_async_client.return_value.__aenter__.return_value.post.assert_not_called()
    mock_async_client.return_value.__aenter__.return_value.get.assert_not_called()
    assert f"Unsupported HTTP method for webhook: {method}" in caplog.text


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
