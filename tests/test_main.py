# tests/test_main.py
import pytest
from unittest.mock import patch, mock_open
from switchbot_exporter.main import load_config, main
import yaml
import asyncio

@patch("builtins.open", new_callable=mock_open, read_data="prometheus_exporter:\n  port: 8888")
def test_load_config(mock_file):
    """Test loading a simple config."""
    config = load_config('dummy_path.yaml')
    assert config['prometheus_exporter']['port'] == 8888

@patch("builtins.open", new_callable=mock_open)
def test_load_config_file_not_found(mock_file):
    """Test that the application exits if config file is not found."""
    mock_file.side_effect = FileNotFoundError
    with pytest.raises(SystemExit):
        load_config('non_existent.yaml')

@patch("builtins.open", new_callable=mock_open, read_data="invalid_yaml: [}")
def test_load_config_yaml_error(mock_file):
    """Test that the application exits on YAML parsing error."""
    with pytest.raises(SystemExit):
        load_config('invalid.yaml')

@patch('switchbot_exporter.main.SwitchbotManager')
@patch('switchbot_exporter.main.PrometheusExporter')
@patch('switchbot_exporter.main.EventDispatcher')
@patch('switchbot_exporter.main.load_config')
@pytest.mark.asyncio
async def test_main_initialization(mock_load_config, mock_dispatcher, mock_exporter, mock_manager):
    """Test that main initializes components based on config."""
    mock_load_config.return_value = {
        'prometheus_exporter': {'enabled': True, 'port': 9090, 'target': {}},
        'actions': [{'name': 'test_action'}]
    }

    # We need to patch the asyncio.sleep to prevent the test from running forever
    with patch('asyncio.sleep', side_effect=asyncio.CancelledError):
        try:
            await main()
        except asyncio.CancelledError:
            pass

    mock_exporter.assert_called_once()
    mock_dispatcher.assert_called_once()
    mock_manager.assert_called_once()
    mock_exporter.return_value.start_server.assert_called_once()
    mock_manager.return_value.start_scan.assert_called_once()
