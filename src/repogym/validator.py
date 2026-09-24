"""Structural task validation."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from repogym.exceptions import SecurityError, TaskLoadError
from repogym.loader import load_task
from repogym.models import TaskSpec
from repogym.security import safe_join, validate_relative_path


@dataclass(frozen=True)
class ValidationReport:
    task: TaskSpec | None
    checks: list[str]
    errors: list[str]
    public_tests: int = 0
    private_tests: int = 0

    @property
    def valid(self) -> bool:
        return not self.errors


def _count_tests(directory: Path) -> tuple[int, list[str]]:
    count = 0
    errors: list[str] = []
    for path in directory.glob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"Could not inspect test file {path.name}: {exc}")
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                count += 1
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                count += sum(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name.startswith("test_")
                    for item in node.body
                )
    return count, errors


def _patterns_conflict(allowed: str, forbidden: str) -> bool:
    def prefix(pattern: str) -> tuple[str, ...]:
        return tuple(
            part for part in PurePosixPath(pattern.replace("\\", "/")).parts if "*" not in part
        )

    a_parts = prefix(allowed)
    f_parts = prefix(forbidden)
    return bool(
        a_parts
        and f_parts
        and (
            a_parts == f_parts
            or a_parts[: len(f_parts)] == f_parts
            or f_parts[: len(a_parts)] == a_parts
        )
    )


def validate_task(task_directory: Path) -> ValidationReport:
    checks: list[str] = []
    errors: list[str] = []
    try:
        task = load_task(task_directory)
    except TaskLoadError as exc:
        return ValidationReport(None, checks, [str(exc)])
    task_dir = task_directory.resolve()
    checks.extend(["task.yaml is valid", "scoring weights total 100"])

    for field, value in (
        ("description_file", task.description_file),
        ("execution.working_directory", task.execution.working_directory),
    ):
        try:
            validate_relative_path(value, field)
        except SecurityError as exc:
            errors.append(str(exc))
    for field, patterns in (
        ("constraints.allowed_paths", task.constraints.allowed_paths),
        ("constraints.forbidden_paths", task.constraints.forbidden_paths),
    ):
        for value in patterns:
            try:
                validate_relative_path(value, field)
            except SecurityError as exc:
                errors.append(str(exc))

    required = {
        "prompt.md": "prompt.md exists",
        "starter": "starter project exists",
        "tests/public": "public tests directory exists",
        "tests/private": "private tests directory exists",
        "reference/solution.patch": "reference solution patch exists",
    }
    if task.description_file != "prompt.md":
        required[task.description_file] = "description file exists"
    for relative, message in required.items():
        try:
            path = safe_join(task_dir, relative)
        except SecurityError as exc:
            errors.append(str(exc))
            continue
        if path.exists() and (
            path.is_dir()
            if relative in {"starter", "tests/public", "tests/private"}
            else path.is_file()
        ):
            checks.append(message)
        else:
            directory_paths = {"starter", "tests/public", "tests/private"}
            kind = "directory" if relative in directory_paths else "file"
            errors.append(f"Missing required {kind}: {relative}")

    try:
        working_directory = safe_join(task_dir / "starter", task.execution.working_directory)
        if not working_directory.is_dir():
            value = task.execution.working_directory
            errors.append(f"Execution working directory does not exist in starter: {value}")
    except SecurityError as exc:
        errors.append(str(exc))

    public_count, public_errors = _count_tests(task_dir / "tests" / "public")
    private_count, private_errors = _count_tests(task_dir / "tests" / "private")
    errors.extend(public_errors)
    errors.extend(private_errors)
    if public_count:
        checks.append(f"public tests discovered: {public_count}")
    else:
        errors.append("No public test files matching test_*.py")
    if private_count:
        checks.append(f"private tests discovered: {private_count}")
    else:
        errors.append("No private test files matching test_*.py")

    for allowed in task.constraints.allowed_paths:
        for forbidden in task.constraints.forbidden_paths:
            if _patterns_conflict(allowed, forbidden):
                errors.append(f"Path constraints conflict: {allowed!r} and {forbidden!r}")
    return ValidationReport(task, checks, errors, public_count, private_count)
