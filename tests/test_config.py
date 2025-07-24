from unittest.mock import mock_open, patch

import pytest

from switchbot_actions.config import AppSettings


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="prometheus_exporter:\n  port: 8888",
)
def test_load_config(mock_file):
    """Test loading a simple config."""
    config = AppSettings.load_from_yaml("dummy_path.yaml")
    assert config["prometheus_exporter"]["port"] == 8888


@patch("builtins.open", new_callable=mock_open)
def test_load_config_file_not_found(mock_file):
    """Test that the application returns a default config if file is not found."""
    mock_file.side_effect = FileNotFoundError
    config = AppSettings.load_from_yaml("non_existent.yaml")
    assert config == {}


@patch("builtins.open", new_callable=mock_open, read_data="invalid_yaml: [{")
def test_load_config_yaml_error(mock_file):
    """Test that the application exits on YAML parsing error."""
    with pytest.raises(SystemExit):
        AppSettings.load_from_yaml("invalid.yaml")
