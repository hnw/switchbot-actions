# tests/test_triggers.py
from unittest.mock import MagicMock, patch

import pytest
import requests

from switchbot_actions import triggers


# --- Fixtures ---
@pytest.fixture
def mock_advertisement_meter():
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:11:11"
    adv.rssi = -70
    adv.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 29.0, "humidity": 65, "battery": 80},
    }
    return adv


@pytest.fixture
def mock_advertisement_meter_old():
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:11:11"
    adv.rssi = -80  # Different RSSI
    adv.data = {
        "modelName": "WoSensorTH",
        "data": {"temperature": 27.0, "humidity": 65, "battery": 80},
    }
    return adv


@pytest.fixture
def mock_advertisement_bot():
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:22:22"
    adv.rssi = -55
    adv.data = {"modelName": "WoHand", "data": {"isOn": True, "battery": 95}}
    return adv


@pytest.fixture
def mock_advertisement_bot_off():
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:22:22"
    adv.rssi = -55
    adv.data = {"modelName": "WoHand", "data": {"isOn": False, "battery": 95}}
    return adv


# --- Tests for check_conditions (which uses evaluate_condition) ---
@pytest.mark.parametrize(
    "conditions, new_data_fixture, should_match",
    [
        # Device conditions
        (
            {"device": {"address": "DE:AD:BE:EF:11:11"}},
            "mock_advertisement_meter",
            True,
        ),
        ({"device": {"modelName": "WoSensorTH"}}, "mock_advertisement_meter", True),
        (
            {"device": {"address": "DE:AD:BE:EF:99:99"}},
            "mock_advertisement_meter",
            False,
        ),
        # State conditions (standard)
        ({"state": {"isOn": True}}, "mock_advertisement_bot", True),
        ({"state": {"temperature": "> 28.0"}}, "mock_advertisement_meter", True),
        ({"state": {"temperature": "< 28.0"}}, "mock_advertisement_meter", False),
        # RSSI conditions
        ({"state": {"rssi": "> -75"}}, "mock_advertisement_meter", True),
        ({"state": {"rssi": "< -75"}}, "mock_advertisement_meter", False),
    ],
)
def test_check_conditions(conditions, new_data_fixture, should_match, request):
    new_data = request.getfixturevalue(new_data_fixture)
    assert triggers.check_conditions(conditions, new_data) == should_match


# --- Tests for format_string ---
def test_format_string(mock_advertisement_meter):
    template = "Temp: {temperature}, Hum: {humidity}, RSSI: {rssi}, Addr: {address}"
    result = triggers.format_string(template, mock_advertisement_meter)
    assert result == "Temp: 29.0, Hum: 65, RSSI: -70, Addr: DE:AD:BE:EF:11:11"


# --- Tests for trigger_action ---
@patch("subprocess.run")
def test_trigger_action_shell(mock_run, mock_advertisement_bot):
    trigger_config = {
        "type": "shell_command",
        "command": "echo 'Bot {address} pressed'",
    }
    triggers.trigger_action(trigger_config, mock_advertisement_bot)
    mock_run.assert_called_once_with(
        "echo 'Bot DE:AD:BE:EF:22:22 pressed'", shell=True, check=False
    )


@patch("requests.post")
def test_trigger_action_webhook_post(mock_post, mock_advertisement_meter):
    trigger_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "method": "POST",
        "payload": {"temp": "{temperature}", "addr": "{address}"},
    }
    triggers.trigger_action(trigger_config, mock_advertisement_meter)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with(
        "http://example.com/hook", json=expected_payload, headers={}, timeout=10
    )


@patch("requests.get")
def test_trigger_action_webhook_get(mock_get, mock_advertisement_meter):
    trigger_config = {
        "type": "webhook",
        "url": "http://example.com/get_hook",
        "method": "GET",
        "payload": {"hum": "{humidity}"},
    }
    triggers.trigger_action(trigger_config, mock_advertisement_meter)
    expected_params = {"hum": "65"}
    mock_get.assert_called_once_with(
        "http://example.com/get_hook", params=expected_params, headers={}, timeout=10
    )


@patch("requests.post")
def test_trigger_action_webhook_with_headers(mock_post, mock_advertisement_meter):
    """Test that webhook triggers can include custom formatted headers."""
    trigger_config = {
        "type": "webhook",
        "url": "http://example.com/hook",
        "payload": {"temp": "{temperature}"},
        "headers": {
            "Authorization": "Bearer MY_TOKEN",
            "X-Device-Address": "{address}",
        },
    }
    triggers.trigger_action(trigger_config, mock_advertisement_meter)
    expected_payload = {"temp": "29.0"}
    expected_headers = {
        "Authorization": "Bearer MY_TOKEN",
        "X-Device-Address": "DE:AD:BE:EF:11:11",
    }
    mock_post.assert_called_once_with(
        "http://example.com/hook",
        json=expected_payload,
        headers=expected_headers,
        timeout=10,
    )


@patch("logging.Logger.warning")
def test_trigger_action_unknown(mock_log_warning, mock_advertisement_bot):
    trigger_config = {"type": "non_existent_type"}
    triggers.trigger_action(trigger_config, mock_advertisement_bot)
    mock_log_warning.assert_called_once_with("Unknown trigger type: non_existent_type")


@patch("requests.post")
@patch("logging.Logger.error")
def test_trigger_action_webhook_failure(
    mock_log_error, mock_post, mock_advertisement_meter
):
    mock_post.side_effect = requests.RequestException("Test connection error")
    trigger_config = {
        "type": "webhook",
        "url": "http://fail.example.com",
        "method": "POST",
    }
    triggers.trigger_action(trigger_config, mock_advertisement_meter)
    mock_log_error.assert_called_once_with("Webhook failed: Test connection error")
