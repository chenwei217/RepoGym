from __future__ import annotations

from pathlib import Path

import pytest

from repogym.commands import split_command
from repogym.exceptions import ValidationError
from repogym.models import ExecutionResult
from repogym.testing import inject_tests, run_tests


class RecordingExecutor:
    def __init__(self) -> None:
        self.command: list[str] = []
        self.cwd: Path | None = None

    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        self.command = command
        self.cwd = cwd
        return ExecutionResult(
            command=command,
            return_code=0,
            stdout="2 passed",
            stderr="",
            duration_seconds=0.1,
        )


def test_split_command() -> None:
    assert split_command('python -m pytest -q "tests/public"')[-1] == "tests/public"


def test_split_command_rejects_unclosed_quote() -> None:
    with pytest.raises(ValidationError, match="Invalid test command"):
        split_command('python "unterminated')


def test_inject_and_run_selected_tests(valid_task: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inject_tests(valid_task, workspace)
    executor = RecordingExecutor()
    task = __import__("repogym.loader", fromlist=["load_task"]).load_task(valid_task)
    result = run_tests(task, workspace, executor, "tests/public")
    assert (workspace / "tests" / "public" / "test_public.py").is_file()
    assert executor.command[-1] == "tests/public"
    assert executor.cwd == workspace
    assert result.return_code == 0
