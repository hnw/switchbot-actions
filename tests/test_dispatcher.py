import pytest
from unittest.mock import MagicMock, patch
from switchbot_exporter.dispatcher import EventDispatcher

@pytest.fixture
def mock_advertisement_meter():
    """Creates a mock SwitchBotAdvertisement for a Meter device."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:11:11"
    adv.data = {
        'modelName': 'Meter',
        'data': {
            'temperature': 29.0,
            'humidity': 65,
            'battery': 80
        }
    }
    return adv

@pytest.fixture
def mock_advertisement_bot():
    """Creates a mock SwitchBotAdvertisement for a Bot device."""
    adv = MagicMock()
    adv.address = "DE:AD:BE:EF:22:22"
    adv.data = {
        'modelName': 'Bot',
        'data': {
            'isOn': True,
            'battery': 95
        }
    }
    return adv

# Test cases for condition matching
@pytest.mark.parametrize("conditions, advertisement_fixture, should_match", [
    # Simple match by address
    ({"address": "DE:AD:BE:EF:11:11"}, "mock_advertisement_meter", True),
    ({"address": "DE:AD:BE:EF:99:99"}, "mock_advertisement_meter", False),
    # Match by model name
    ({"modelName": "Meter"}, "mock_advertisement_meter", True),
    ({"modelName": "Bot"}, "mock_advertisement_meter", False),
    # Match by nested data
    ({"data": {"isOn": True}}, "mock_advertisement_bot", True),
    ({"data": {"isOn": False}}, "mock_advertisement_bot", False),
    # Match by numeric operator: greater than
    ({"data": {"temperature": "> 28.0"}}, "mock_advertisement_meter", True),
    ({"data": {"temperature": "> 30.0"}}, "mock_advertisement_meter", False),
    # Match by numeric operator: less than or equal to
    ({"data": {"humidity": "<= 65"}}, "mock_advertisement_meter", True),
    ({"data": {"humidity": "< 65"}}, "mock_advertisement_meter", False),
    # Complex match
    ({"address": "DE:AD:BE:EF:22:22", "modelName": "Bot", "data": {"isOn": True}}, "mock_advertisement_bot", True),
    ({"address": "DE:AD:BE:EF:22:22", "data": {"isOn": False}}, "mock_advertisement_bot", False),
    # Condition key does not exist in advertisement
    ({"data": {"non_existent_key": True}}, "mock_advertisement_bot", False),
])
def test_conditions_met(conditions, advertisement_fixture, should_match, request):
    advertisement = request.getfixturevalue(advertisement_fixture)
    dispatcher = EventDispatcher(actions_config=[])
    assert dispatcher._conditions_met(conditions, advertisement) == should_match

@patch('subprocess.run')
def test_shell_command_trigger(mock_run, mock_advertisement_bot):
    """Test that a shell command action is correctly triggered."""
    actions_config = [{
        "name": "Test Shell Action",
        "event_conditions": {"modelName": "Bot", "data": {"isOn": True}},
        "trigger": {"type": "shell_command", "command": "echo 'Bot pressed'"}
    }]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_advertisement(None, device_data=mock_advertisement_bot)
    mock_run.assert_called_once_with("echo 'Bot pressed'", shell=True, check=False)

@patch('requests.post')
def test_webhook_post_trigger(mock_post, mock_advertisement_meter):
    """Test that a POST webhook action is correctly triggered."""
    actions_config = [{
        "name": "Test Webhook Action",
        "event_conditions": {"data": {"temperature": "> 28.0"}},
        "trigger": {
            "type": "webhook",
            "url": "http://test.com/hook",
            "method": "POST",
            "payload": {"temp": "{temperature}", "addr": "{address}"}
        }
    }]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_advertisement(None, device_data=mock_advertisement_meter)
    
    expected_payload = {"temp": "29.0", "addr": "DE:AD:BE:EF:11:11"}
    mock_post.assert_called_once_with("http://test.com/hook", json=expected_payload, timeout=10)

@patch('requests.get')
def test_webhook_get_trigger(mock_get, mock_advertisement_meter):
    """Test that a GET webhook action is correctly triggered."""
    actions_config = [{
        "name": "Test GET Webhook",
        "event_conditions": {"modelName": "Meter"},
        "trigger": {
            "type": "webhook",
            "url": "http://test.com/get_hook",
            "method": "GET",
            "payload": {"hum": "{humidity}"}
        }
    }]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_advertisement(None, device_data=mock_advertisement_meter)
    
    expected_params = {"hum": "65"}
    mock_get.assert_called_once_with("http://test.com/get_hook", params=expected_params, timeout=10)

@patch('logging.Logger.warning')
def test_unknown_trigger_type(mock_log_warning, mock_advertisement_bot):
    """Test that an unknown trigger type logs a warning."""
    actions_config = [{
        "name": "Unknown Trigger Test",
        "event_conditions": {"modelName": "Bot"},
        "trigger": {"type": "non_existent_type"}
    }]
    dispatcher = EventDispatcher(actions_config=actions_config)
    dispatcher.handle_advertisement(None, device_data=mock_advertisement_bot)
    mock_log_warning.assert_called_once_with("Unknown trigger type: non_existent_type")

def test_no_trigger_if_conditions_not_met(mock_advertisement_bot):
    """Test that no action is triggered if conditions are not met."""
    with patch('subprocess.run') as mock_run, patch('requests.post') as mock_post:
        actions_config = [{
            "name": "Test No-Match Action",
            "event_conditions": {"data": {"isOn": False}}, # This will not match
            "trigger": {"type": "shell_command", "command": "echo 'Should not run'"}
        }]
        dispatcher = EventDispatcher(actions_config=actions_config)
        dispatcher.handle_advertisement(None, device_data=mock_advertisement_bot)
        mock_run.assert_not_called()
        mock_post.assert_not_called()
