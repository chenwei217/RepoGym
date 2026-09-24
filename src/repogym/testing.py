"""Helpers shared by verification and grading."""

from __future__ import annotations

import re
from pathlib import Path

from repogym.commands import resolve_command
from repogym.executors.base import Executor
from repogym.models import ExecutionResult, TaskSpec, TestCounts
from repogym.security import copy_tree_safe, safe_join

COUNT_PATTERNS = {
    "passed": re.compile(r"(\d+) passed"),
    "failed": re.compile(r"(\d+) failed"),
    "errors": re.compile(r"(\d+) errors?"),
}


def inject_tests(task_directory: Path, workspace: Path) -> None:
    copy_tree_safe(task_directory / "tests" / "public", workspace / "tests" / "public")
    copy_tree_safe(task_directory / "tests" / "private", workspace / "tests" / "private")


def parse_test_counts(result: ExecutionResult) -> TestCounts:
    combined = f"{result.stdout}\n{result.stderr}"
    values: dict[str, int] = {}
    for name, pattern in COUNT_PATTERNS.items():
        matches = pattern.findall(combined)
        values[name] = int(matches[-1]) if matches else 0
    failed = values["failed"] + values["errors"]
    return TestCounts(passed=values["passed"], failed=failed, total=values["passed"] + failed)


def run_tests(
    task: TaskSpec,
    workspace: Path,
    executor: Executor,
    selection: str | None = None,
) -> ExecutionResult:
    command = resolve_command(task.execution.test_command)
    if selection is not None:
        command.append(selection)
    cwd = safe_join(workspace, task.execution.working_directory)
    return executor.execute(command, cwd, task.execution.timeout_seconds)
