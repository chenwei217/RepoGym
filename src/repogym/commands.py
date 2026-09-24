"""Cross-platform command parsing."""

from __future__ import annotations

import os
import shlex
import sys

from repogym.exceptions import ValidationError


def split_command(command: str) -> list[str]:
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError as exc:
        raise ValidationError(f"Invalid test command: {exc}") from exc
    if os.name == "nt":
        parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts
        ]
    if not parts:
        raise ValidationError("Test command must not be empty")
    return parts


def resolve_command(command: str) -> list[str]:
    """Parse a task command and bind generic Python launchers to this runtime."""
    parts = split_command(command)
    if parts[0] in {"python", "python.exe"}:
        parts[0] = sys.executable
    return parts
