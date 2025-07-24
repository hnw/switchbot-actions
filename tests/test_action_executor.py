from unittest.mock import MagicMock, patch

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
@patch("subprocess.run")
def test_execute_action_shell(mock_run):
    state_object = MagicMock()
    state_object.address = "DE:AD:BE:EF:22:22"
    state_object.rssi = -55
    state_object.data = {"modelName": "WoHand", "data": {"isOn": True, "battery": 95}}
    action_config = {
        "type": "shell_command",
        "command": "echo 'Bot {address} pressed'",
    }
    action_executor.execute_action(action_config, state_object)
    mock_run.assert_called_once_with(
        "echo 'Bot DE:AD:BE:EF:22:22 pressed'", shell=True, check=False
    )


@patch("requests.post")
def test_execute_action_webhook_post(mock_post):
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
    action_executor.execute_action(action_config, state_object)
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with(
        "http://example.com/hook", json=expected_payload, headers={}, timeout=10
    )
