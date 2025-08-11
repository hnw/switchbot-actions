from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import ValidationError
from ruamel.yaml.comments import CommentedMap, CommentedSeq


class ConfigError(Exception):
    """Custom exception for configuration-related errors."""

    pass


def get_error_snippet(
    config_path: Path, error_lc, context_lines: int = 2
) -> Optional[str]:
    """Extracts a snippet of YAML from the config file around the error location."""
    try:
        with open(config_path, "r") as f:
            lines = f.readlines()
    except (IOError, OSError):
        return None

    # Ensure context_lines is non-negative
    context_lines = max(0, context_lines)
    num_lines = len(lines)
    if error_lc[0] >= num_lines:
        error_lc = (num_lines - 1, 0)

    start_line = max(0, error_lc[0] - context_lines)
    end_line = min(num_lines, error_lc[0] + context_lines + 1)

    snippet_lines = []
    for i in range(start_line, end_line):
        prefix = "> " if i == error_lc[0] else "  "
        snippet_lines.append(f"{prefix}{i + 1:^4}| {lines[i].rstrip()}")

    return "\n".join(snippet_lines)


def generate_hybrid_error_message(error: Dict[str, Any]) -> str:
    """Generates a user-friendly error message based on the Pydantic error type."""
    error_type = error.get("type")
    if error_type == "missing":
        field_name = error.get("loc", [])[-1]
        return f"Required field '{field_name}' is missing"
    elif error_type == "extra_forbidden":
        field_name = error.get("loc", [])[-1]
        return f"Unexpected field '{field_name}'"

    return error.get("msg") or "An unknown validation error occurred."


def format_validation_error(
    e: ValidationError, config_path: Path, config_data: dict
) -> str:
    """Formats a Pydantic ValidationError into a user-friendly string."""
    error_messages = [f"Configuration Error in '{config_path}':"]
    prev_lc = None

    def get_lc(node):
        if hasattr(node, "lc"):
            return (node.lc.line, node.lc.col)
        return None

    def get_child_lc(parent, key_or_index):
        if isinstance(parent, CommentedMap):
            return parent.lc.value(key_or_index)
        if isinstance(parent, CommentedSeq):
            return parent.lc.item(key_or_index)
        return None

    for i, error in enumerate(e.errors()):
        node_with_line_info = error.get("input")
        error_lc = get_lc(node_with_line_info)
        if error_lc is None:
            path = list(error.get("loc", []))  # Convert tuple to list for mutability
            if path:
                parent_path = path[:-1]
                parent_node = config_data
                for item in parent_path:
                    try:
                        parent_node = parent_node[item]
                    except (KeyError, IndexError, TypeError):
                        pass
                error_lc = get_child_lc(parent_node, path[-1])
                if error_lc is None:
                    error_lc = get_lc(parent_node)

        snippet = None
        if error_lc:
            snippet = get_error_snippet(config_path, error_lc)
            if prev_lc is not None and error_lc[0] == prev_lc[0]:
                snippet = None

        if snippet:
            error_messages.append("")
            error_messages.append(f"{snippet}")

        message = generate_hybrid_error_message(error)  # type: ignore[arg-type]

        if error_lc is not None:
            if prev_lc is None or error_lc[0] != prev_lc[0]:
                error_messages.append("")
            error_messages.append(f"Error at line {error_lc[0] + 1}: {message}")
            prev_lc = error_lc
        else:
            error_messages.append("")
            error_path = ".".join(map(str, error["loc"]))
            error_messages.append(f"Error at '{error_path}': {message}")
            prev_lc = None

    return "\n".join(error_messages)
