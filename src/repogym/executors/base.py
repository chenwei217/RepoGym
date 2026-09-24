"""Executor protocol."""

from pathlib import Path
from typing import Protocol

from repogym.models import ExecutionResult


class Executor(Protocol):
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult: ...
