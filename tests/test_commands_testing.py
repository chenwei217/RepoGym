from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from repogym.commands import resolve_command, split_command
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


@pytest.mark.parametrize("launcher", ["python", "python.exe"])
def test_resolve_command_binds_generic_python_to_active_interpreter(launcher: str) -> None:
    assert resolve_command(f"{launcher} -m pytest -q") == [sys.executable, "-m", "pytest", "-q"]


def test_resolve_command_preserves_absolute_python_path() -> None:
    executable = r"C:\custom-python\python.exe" if os.name == "nt" else "/custom-python/python"
    assert resolve_command(f'"{executable}" -V') == [executable, "-V"]


def test_resolve_command_preserves_non_python_command() -> None:
    assert resolve_command("pytest -q") == ["pytest", "-q"]


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


def test_run_tests_ignores_an_unrelated_python_on_path(
    valid_task: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / ("python.exe" if os.name == "nt" else "python")
    fake_python.write_text("not the active interpreter\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = RecordingExecutor()
    task = __import__("repogym.loader", fromlist=["load_task"]).load_task(valid_task)

    run_tests(task, workspace, executor)

    assert executor.command[0] == sys.executable
    assert executor.command[0] != str(fake_python)
