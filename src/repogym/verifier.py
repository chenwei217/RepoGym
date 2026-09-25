"""End-to-end verification of task design."""

from __future__ import annotations

import fnmatch
import tempfile
from dataclasses import dataclass
from pathlib import Path

from repogym.exceptions import ExecutionError, ValidationError
from repogym.executors.base import CancellationToken, Executor
from repogym.executors.local import LocalExecutor
from repogym.models import ExecutionResult
from repogym.patching import apply_patch, patch_paths
from repogym.reproducibility import task_fingerprint
from repogym.security import copy_tree_safe
from repogym.testing import inject_tests, parse_test_counts, run_tests
from repogym.validator import validate_task


@dataclass(frozen=True)
class VerificationReport:
    task_id: str
    task_fingerprint: str
    initial: ExecutionResult
    fixed: ExecutionResult
    patch_files: list[str]


def _matches(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    if normalized.endswith("/**"):
        return path.startswith(normalized[:-3].rstrip("/") + "/")
    return fnmatch.fnmatchcase(path, normalized)


def verify_task(
    task_directory: Path,
    executor: Executor | None = None,
    cancellation_token: CancellationToken | None = None,
) -> VerificationReport:
    validation = validate_task(task_directory)
    if not validation.valid or validation.task is None:
        raise ValidationError("Task validation failed:\n  - " + "\n  - ".join(validation.errors))
    task = validation.task
    task_dir = task_directory.resolve()
    fingerprint = task_fingerprint(task_dir, task)
    patch_text = (task_dir / "reference" / "solution.patch").read_text(encoding="utf-8")
    paths = patch_paths(patch_text)
    forbidden = [
        path
        for path in paths
        if any(_matches(path, pattern) for pattern in task.constraints.forbidden_paths)
    ]
    if forbidden:
        raise ValidationError(f"Reference patch modifies forbidden paths: {', '.join(forbidden)}")
    runner = executor or LocalExecutor()
    with tempfile.TemporaryDirectory(prefix="repogym-verify-") as temporary:
        workspace = Path(temporary) / "workspace"
        copy_tree_safe(task_dir / "starter", workspace)
        inject_tests(task_dir, workspace)
        initial = run_tests(task, workspace, runner, cancellation_token=cancellation_token)
        initial_counts = parse_test_counts(initial)
        if initial.cancelled:
            raise ExecutionError("Initial test run was cancelled")
        if initial.timed_out:
            raise ExecutionError("Initial test run timed out")
        if initial_counts.failed != task.expected.failing_tests_before:
            raise ExecutionError(
                "Initial failure count mismatch: "
                f"expected {task.expected.failing_tests_before}, got {initial_counts.failed}"
            )
        apply_patch(workspace, patch_text)
        fixed = run_tests(task, workspace, runner, cancellation_token=cancellation_token)
        fixed_counts = parse_test_counts(fixed)
        if fixed.cancelled:
            raise ExecutionError("Reference solution test run was cancelled")
        if fixed.timed_out:
            raise ExecutionError("Reference solution test run timed out")
        if fixed.return_code != 0 or fixed_counts.failed != 0:
            raise ExecutionError("Reference solution does not pass all tests")
        if fixed_counts.passed != task.expected.passing_tests_after:
            raise ExecutionError(
                "Reference passing count mismatch: "
                f"expected {task.expected.passing_tests_after}, got {fixed_counts.passed}"
            )
        return VerificationReport(task.id, fingerprint, initial, fixed, paths)
