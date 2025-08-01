import argparse
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from ruamel.yaml.error import YAMLError

from switchbot_actions.config_loader import load_settings_from_cli
from switchbot_actions.error import ConfigError


@patch(
    "switchbot_actions.config_loader.format_validation_error",
    return_value="Mocked Validation Error Output",
)
def test_load_settings_from_cli_invalid_config_missing_field(
    mock_format_validation_error, tmp_path
):
    """Test that load_settings_from_cli handles a missing field error and exits."""
    invalid_config_content = """
automations:
  - name: "Turn off Lights if No Motion for 3 Minutes"
    then:
      - type: shell_command
        command: "echo 'hello'"
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    # Create a mock args object
    mock_args = argparse.Namespace(config=str(config_file))

    with pytest.raises(ConfigError) as e:
        load_settings_from_cli(mock_args)

    assert str(e.value) == "Mocked Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], ValidationError)  # Check if it's a
    # ValidationError instance
    assert args[1] == config_file
    assert isinstance(args[2], dict)  # Check if it's the config_data


def test_load_settings_from_cli_overrides_config_with_cli_args(tmp_path):
    """Test that CLI arguments correctly override values loaded from a config file."""
    # 1. Create a temporary YAML config file with some default values.
    config_content = """
debug: false
scanner:
  cycle: 10
  duration: 5
  interface: 0
mqtt:
  host: "localhost"
  port: 1883
  username: "user"
  password: "password"
  reconnect_interval: 60
logging:
  level: "INFO"
prometheus_exporter:
  enabled: false
  port: 8000
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    # 2. Create a mock argparse.Namespace object with some command-line arguments
    #    that should override the config file values.
    mock_args = argparse.Namespace(
        config=str(config_file),
        debug=True,
        scan_cycle=20,
        mqtt_host="mqtt.example.com",
        mqtt_port=8883,
        log_level="DEBUG",
        prometheus_exporter_enabled=True,
        prometheus_exporter_port=9000,
        scan_duration=None,  # Should not override if None
        interface=None,  # Should not override if None
        mqtt_username=None,  # Should not override if None
        mqtt_password=None,  # Should not override if None
        mqtt_reconnect_interval=None,  # Should not override if None
    )

    # 3. Call load_settings_from_cli with the mock arguments.
    settings = load_settings_from_cli(mock_args)

    # 4. Assert that the returned AppSettings object has the values correctly
    #    overridden by the command-line arguments.
    assert settings.debug is True
    assert settings.scanner.cycle == 20
    assert settings.scanner.duration == 5  # Not overridden
    assert settings.scanner.interface == 0  # Not overridden
    assert settings.mqtt is not None
    assert settings.mqtt.host == "mqtt.example.com"
    assert settings.mqtt.port == 8883
    assert settings.mqtt.username == "user"  # Not overridden
    assert settings.mqtt.password == "password"  # Not overridden
    assert settings.mqtt.reconnect_interval == 60  # Not overridden
    assert settings.logging.level == "DEBUG"
    assert settings.prometheus_exporter.enabled is True
    assert settings.prometheus_exporter.port == 9000


@patch(
    "switchbot_actions.config_loader.format_validation_error",
    return_value="Mocked Enum Validation Error Output",
)
def test_load_settings_from_cli_invalid_config_enum(
    mock_format_validation_error, tmp_path
):
    """Test that load_settings_from_cli handles an enum error and exits."""
    invalid_config_content = """
logging:
  level: "DETAIL"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    # Create a mock args object
    mock_args = argparse.Namespace(config=str(config_file))

    with pytest.raises(ConfigError) as e:
        load_settings_from_cli(mock_args)

    assert str(e.value) == "Mocked Enum Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], ValidationError)
    assert args[1] == config_file
    assert isinstance(args[2], dict)


def test_load_settings_from_cli_yaml_syntax_error(tmp_path):
    """
    Test that load_settings_from_cli handles YAML syntax errors with detailed output.
    """
    invalid_yaml_content = """
automations:
  - name: "Invalid Indent"
    then:
      - type: shell_command
        command: "echo 'hello'"
    invalid_key value # This line has an invalid indent (missing colon)
"""
    config_file = tmp_path / "invalid_syntax.yaml"
    config_file.write_text(invalid_yaml_content)

    mock_args = argparse.Namespace(config=str(config_file))

    with pytest.raises(ConfigError) as e:
        load_settings_from_cli(mock_args)

    assert "YAML Parsing Error in " in str(e.value)
    assert str(config_file) in str(e.value)
    assert ">  7  |     invalid_key value" in str(e.value)
    assert "Error at line 8:" in str(e.value)
    assert "could not find expected ':'" in str(e.value)


def test_prometheus_exporter_precedence(tmp_path):
    """
    Test that command-line arguments correctly override config file settings
    for prometheus_exporter_enabled.
    """

    # Test Case 1: Config File Priority (enabled: true, no CLI arg)
    config_content_true = """
prometheus_exporter:
  enabled: true
  port: 8000
"""
    config_file_true = tmp_path / "config_true.yaml"
    config_file_true.write_text(config_content_true)

    mock_args_1 = argparse.Namespace(
        config=str(config_file_true),
        prometheus_exporter_enabled=None,  # No CLI override
    )
    settings_1 = load_settings_from_cli(mock_args_1)
    assert settings_1.prometheus_exporter.enabled is True

    # Test Case 2: Positive Flag Override (config: false,
    # CLI: --prometheus-exporter-enabled)
    config_content_false = """
prometheus_exporter:
  enabled: false
  port: 8000
"""
    config_file_false = tmp_path / "config_false.yaml"
    config_file_false.write_text(config_content_false)

    mock_args_2 = argparse.Namespace(
        config=str(config_file_false),
        prometheus_exporter_enabled=True,  # CLI override to True
    )
    settings_2 = load_settings_from_cli(mock_args_2)
    assert settings_2.prometheus_exporter.enabled is True

    # Test Case 3: Negative Flag Override (config: true,
    # CLI: --no-prometheus-exporter-enabled)
    config_content_true_again = """
prometheus_exporter:
  enabled: true
  port: 8000
"""
    config_file_true_again = tmp_path / "config_true_again.yaml"
    config_file_true_again.write_text(config_content_true_again)

    mock_args_3 = argparse.Namespace(
        config=str(config_file_true_again),
        prometheus_exporter_enabled=False,  # CLI override to False
    )
    settings_3 = load_settings_from_cli(mock_args_3)
    assert settings_3.prometheus_exporter.enabled is False


@patch(
    "switchbot_actions.config_loader.YAML",
)
def test_load_settings_from_cli_yaml_syntax_error_no_problem_mark(
    mock_yaml_loader, tmp_path
):
    """
    Test that load_settings_from_cli handles YAML syntax errors without problem_mark.
    """

    # Create a dummy config file
    config_file = tmp_path / "dummy_config.yaml"
    config_file.write_text("dummy_content")

    # Mock the YAML loader to raise a YAMLError without problem_mark
    mock_yaml_instance = mock_yaml_loader.return_value
    mock_yaml_instance.load.side_effect = YAMLError("Generic YAML Error")

    mock_args = argparse.Namespace(config=str(config_file))

    with pytest.raises(ConfigError) as e:
        load_settings_from_cli(mock_args)

    assert "YAML Parsing Error: Generic YAML Error" in str(e.value)
    assert ">" not in str(e.value)  # No code snippet expected


@patch(
    "switchbot_actions.config_loader.format_validation_error",
    return_value="Mocked Tag Validation Error Output",
)
def test_load_settings_from_cli_invalid_config_tag(
    mock_format_validation_error, tmp_path
):
    """
    Test that load_settings_from_cli handles a missing required field
    for a specific tag.
    """
    invalid_config_content = """
automations:
  - if:
      source: mqtt
    then:
      type: mqtt-publish
"""
    config_file = tmp_path / "invalid_config.yaml"
    config_file.write_text(invalid_config_content)

    # Create a mock args object
    mock_args = argparse.Namespace(config=str(config_file))

    with pytest.raises(ConfigError) as e:
        load_settings_from_cli(mock_args)

    assert str(e.value) == "Mocked Tag Validation Error Output"
    mock_format_validation_error.assert_called_once()
    args, kwargs = mock_format_validation_error.call_args
    assert isinstance(args[0], ValidationError)
    assert args[1] == config_file
    assert isinstance(args[2], dict)
