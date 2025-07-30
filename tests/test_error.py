from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from switchbot_actions.error import (
    ConfigError,
    format_validation_error,
    generate_hybrid_error_message,
    get_error_snippet,
)


def test_config_error_exception():
    """Test that ConfigError can be raised and caught."""
    with pytest.raises(ConfigError, match="Test error message"):
        raise ConfigError("Test error message")


class MockMark:
    def __init__(self, line, col):
        self.line = line
        self.col = col


@pytest.fixture
def mock_config_path():
    return Path("/tmp/test_config.yaml")


def test_get_error_snippet_basic(tmp_path):
    config_content = "key1: value1\nkey2: value2\nkey3: value3"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    error_lc = (1, 0)  # Points to line 2 (key2)

    snippet = get_error_snippet(config_file, error_lc, context_lines=1)
    expected_snippet = (
        "   1  | key1: value1\n>  2  | key2: value2\n   3  | key3: value3"
    )
    assert snippet is not None
    assert snippet.strip() == expected_snippet.strip()


def test_get_error_snippet_file_errors(tmp_path):
    # Test with a non-existent file
    non_existent_file = tmp_path / "non_existent.yaml"
    error_lc = (0, 0)
    assert get_error_snippet(non_existent_file, error_lc) is None

    # Test with a file that has no read permissions
    no_permission_file = tmp_path / "no_permission.yaml"
    no_permission_file.write_text("some content")
    no_permission_file.chmod(0o000)  # Remove all permissions

    assert get_error_snippet(no_permission_file, error_lc) is None

    # Restore permissions for cleanup
    no_permission_file.chmod(0o644)


def test_get_error_snippet_edge_cases(tmp_path):
    config_content = "line1\nline2\nline3\nline4\nline5"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    # error_lc.line at the beginning (line 0)
    error_lc_start = (0, 0)
    snippet_start = get_error_snippet(config_file, error_lc_start, context_lines=2)
    expected_start = ">  1  | line1\n   2  | line2\n   3  | line3"
    assert snippet_start is not None
    assert snippet_start.strip() == expected_start.strip()

    # error_lc.line at the end (line 4, 5th line)
    error_lc_end = (4, 0)
    snippet_end = get_error_snippet(config_file, error_lc_end, context_lines=2)
    expected_end = "   3  | line3\n   4  | line4\n>  5  | line5"
    assert snippet_end is not None
    assert snippet_end.strip() == expected_end.strip()

    # context_lines = 0
    error_lc_middle = (2, 0)  # Points to line 3
    snippet_zero_context = get_error_snippet(
        config_file, error_lc_middle, context_lines=0
    )
    expected_zero_context = ">  3  | line3"
    assert snippet_zero_context is not None
    assert snippet_zero_context.strip() == expected_zero_context.strip()

    # context_lines = -1 (should behave like 0 due to max(0, ...))
    snippet_negative_context = get_error_snippet(
        config_file, error_lc_middle, context_lines=-1
    )
    assert snippet_negative_context is not None
    assert snippet_negative_context.strip() == expected_zero_context.strip()


def test_generate_hybrid_error_message_missing():
    error = {"type": "missing", "loc": ("field",)}
    message = generate_hybrid_error_message(error)
    assert message == "Required field 'field' is missing"


def test_generate_hybrid_error_message_extra_forbidden():
    error = {"type": "extra_forbidden", "loc": ("field",)}
    message = generate_hybrid_error_message(error)
    assert message == "Unexpected field 'field'"


def test_generate_hybrid_error_message_other():
    error = {"type": "value_error", "msg": "Invalid value"}
    message = generate_hybrid_error_message(error)
    assert message == "Invalid value"


def test_generate_hybrid_error_message_unknown():
    error = {"type": "unknown_error"}
    message = generate_hybrid_error_message(error)
    assert message == "An unknown validation error occurred."


def test_generate_hybrid_error_message_various_types():
    # Test type_error
    error_type = {"type": "type_error", "msg": "Input should be a valid integer"}
    assert (
        generate_hybrid_error_message(error_type) == "Input should be a valid integer"
    )

    # Test value_error
    error_value = {"type": "value_error", "msg": "Value out of range"}
    assert generate_hybrid_error_message(error_value) == "Value out of range"

    # Test json_error
    error_json = {"type": "json_error", "msg": "Invalid JSON format"}
    assert generate_hybrid_error_message(error_json) == "Invalid JSON format"

    # Test empty msg field
    error_empty_msg = {"type": "value_error", "msg": ""}
    assert (
        generate_hybrid_error_message(error_empty_msg)
        == "An unknown validation error occurred."
    )

    # Test missing type with multi-element loc
    error_missing_multi_loc = {
        "type": "missing",
        "loc": ("data", "nested", "field_name"),
    }
    assert (
        generate_hybrid_error_message(error_missing_multi_loc)
        == "Required field 'field_name' is missing"
    )


def test_format_validation_error_multiple_errors(tmp_path):
    config_content = "key1: value1\nkey2: value2\nkey3: value3"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    # Mock a ValidationError with multiple errors
    mock_validation_error_instance = MagicMock(spec=ValidationError)
    mock_validation_error_instance.errors.return_value = [
        {
            "type": "missing",
            "loc": ("key1",),
            "input": MagicMock(lc=MockMark(line=0, col=0)),
            "msg": "Field required",
        },
        {
            "type": "value_error",
            "loc": ("key2",),
            "input": MagicMock(lc=MockMark(line=1, col=0)),
            "msg": "Invalid value",
        },
    ]

    # Mock CommentedMap to have lc attribute
    mock_commented_map_key1 = MagicMock()
    mock_commented_map_key1.lc.line = 0
    mock_commented_map_key1.lc.col = 0

    mock_commented_map_key2 = MagicMock()
    mock_commented_map_key2.lc.line = 1
    mock_commented_map_key2.lc.col = 0

    with patch(
        "switchbot_actions.error.get_error_snippet",
        side_effect=lambda *args, **kwargs: "SNIPPET",
    ):
        with patch(
            "switchbot_actions.error.generate_hybrid_error_message",
            side_effect=["Required field 'key1' is missing", "Invalid value"],
        ):
            # Create a mock ValidationError instance
            formatted_message = format_validation_error(
                mock_validation_error_instance, config_file, {}
            )
            assert "Configuration Error in" in formatted_message
            assert "SNIPPET" in formatted_message
            assert (
                "Error at line 1: Required field 'key1' is missing" in formatted_message
            )
            assert "Error at line 2: Invalid value" in formatted_message


def test_format_validation_error_no_lc_attribute(tmp_path):
    config_content = "key1: value1\nkey2: value2\nkey3: value3"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    # Mock a ValidationError where input has no lc attribute
    # (e.g., basic data type validation)
    mock_validation_error_instance = MagicMock(spec=ValidationError)
    mock_validation_error_instance.errors.return_value = [
        {
            "type": "value_error",
            "loc": ("key1", "nested_field"),
            "input": "not a commented map",
            "msg": "Invalid type",
        },
        {
            "type": "missing",
            "loc": ("list_data", 0, "item_field"),
            "input": "not a commented map",
            "msg": "Field required",
        },
    ]

    with patch("switchbot_actions.error.get_error_snippet", return_value=None):
        with patch(
            "switchbot_actions.error.generate_hybrid_error_message",
            side_effect=["Invalid type", "Required field 'item_field' is missing"],
        ):
            formatted_message = format_validation_error(
                mock_validation_error_instance, config_file, {}
            )
            assert "Configuration Error in" in formatted_message
            assert "Error at 'key1.nested_field': Invalid type" in formatted_message
            assert (
                "Error at 'list_data.0.item_field': "
                "Required field 'item_field' is missing" in formatted_message
            )

    # Test with empty config_data
    mock_validation_error_empty_data = MagicMock(spec=ValidationError)
    mock_validation_error_empty_data.errors.return_value = [
        {
            "type": "missing",
            "loc": ("non_existent_field",),
            "input": "some_value",
            "msg": "Field required",
        }
    ]
    formatted_message_empty_data = format_validation_error(
        mock_validation_error_empty_data, config_file, {}
    )
    assert (
        "Error at 'non_existent_field': Required field 'non_existent_field' is missing"
        in formatted_message_empty_data
    )

    # Test with path not found in config_data
    config_data_partial = {"existing_key": "value"}
    mock_validation_error_path_not_found = MagicMock(spec=ValidationError)
    mock_validation_error_path_not_found.errors.return_value = [
        {
            "type": "missing",
            "loc": ("non_existent_path", "field"),
            "input": "some_value",
            "msg": "Field required",
        }
    ]
    formatted_message_path_not_found = format_validation_error(
        mock_validation_error_path_not_found, config_file, config_data_partial
    )
    assert (
        "Error at 'non_existent_path.field': Required field 'field' is missing"
        in formatted_message_path_not_found
    )


def test_format_validation_error_no_snippet(tmp_path):
    config_content = "key1: value1"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    # Mock a ValidationError where error_lc is None
    mock_validation_error_instance = MagicMock(spec=ValidationError)
    mock_validation_error_instance.errors.return_value = [
        {
            "type": "value_error",
            "loc": ("key1",),
            "input": "some_value",
            "msg": "Invalid value",
        },
    ]

    with patch("switchbot_actions.error.get_error_snippet", return_value=None):
        with patch(
            "switchbot_actions.error.generate_hybrid_error_message",
            return_value="Invalid value",
        ):
            formatted_message = format_validation_error(
                mock_validation_error_instance, config_file, {}
            )
            assert "Configuration Error in" in formatted_message
            assert "SNIPPET" not in formatted_message  # Ensure no snippet is added
            assert "Error at 'key1': Invalid value" in formatted_message
            assert (
                "Error at line" not in formatted_message
            )  # Ensure no line number is added


def test_get_error_snippet_points_to_last_line_on_eof_error(tmp_path):
    config_content = "key1: value1\nkey2: value2"
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)

    error_lc = (2, 0)

    snippet = get_error_snippet(config_file, error_lc, context_lines=1)

    expected_snippet = "   1  | key1: value1\n>  2  | key2: value2"

    assert snippet is not None
    assert snippet.strip() == expected_snippet.strip()
