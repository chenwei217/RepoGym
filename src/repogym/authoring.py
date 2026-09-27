"""Safe task scaffolding and author-oriented diagnostics."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import yaml

from repogym.commands import split_command
from repogym.exceptions import AuthoringError, RepoGymError
from repogym.security import safe_join
from repogym.spec_schema import CURRENT_TASK_SCHEMA_VERSION
from repogym.validator import ValidationReport, validate_task

TASK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER_MARKERS = ("todo", "replace this placeholder")


@dataclass(frozen=True)
class AuthoringDiagnostic:
    status: Literal["warning", "error"]
    code: str
    message: str


@dataclass(frozen=True)
class AuthoringReport:
    validation: ValidationReport
    diagnostics: list[AuthoringDiagnostic]

    @property
    def valid(self) -> bool:
        return self.validation.valid and not any(
            item.status == "error" for item in self.diagnostics
        )


def _task_mapping(task_id: str, title: str, module_name: str) -> dict[str, object]:
    return {
        "schema_version": CURRENT_TASK_SCHEMA_VERSION,
        "id": task_id,
        "title": title,
        "difficulty": "medium",
        "language": "python",
        "version": "1.0",
        "description_file": "prompt.md",
        "execution": {
            "timeout_seconds": 30,
            "test_command": "python -m pytest -q",
            "working_directory": ".",
        },
        "scoring": {
            "correctness": {"weight": 60},
            "regression_safety": {"weight": 20},
            "code_quality": {"weight": 10},
            "scope_control": {"weight": 10},
        },
        "expected": {"failing_tests_before": 2, "passing_tests_after": 2},
        "constraints": {
            "allowed_paths": [f"{module_name}/**", "tests/**"],
            "forbidden_paths": ["pyproject.toml", ".github/**"],
        },
    }


def _write_template(directory: Path, task_id: str, title: str) -> None:
    module_name = task_id.replace("-", "_")
    package = directory / "starter" / module_name
    public = directory / "tests" / "public"
    private = directory / "tests" / "private"
    reference = directory / "reference"
    for path in (package, public, private, reference):
        path.mkdir(parents=True)
    (directory / "task.yaml").write_text(
        yaml.safe_dump(
            _task_mapping(task_id, title, module_name),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (directory / "prompt.md").write_text(
        f"# {title}\n\nTODO: describe observable inputs, outputs, errors, and boundary behavior.\n",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        'from .solution import solve\n\n__all__ = ["solve"]\n',
        encoding="utf-8",
    )
    (package / "solution.py").write_text(
        "def solve(value: int) -> int:\n"
        '    raise NotImplementedError("TODO: implement the task behavior")\n',
        encoding="utf-8",
    )
    for directory_name, value in (("public", 1), ("private", 2)):
        (directory / "tests" / directory_name / "test_solution.py").write_text(
            f"from {module_name} import solve\n\n\n"
            f"def test_todo_{directory_name}_behavior() -> None:\n"
            f"    assert solve({value}) == {value}\n",
            encoding="utf-8",
        )
    (reference / "solution.patch").write_text(
        "# TODO: replace this placeholder with a unified diff that makes all tests pass.\n",
        encoding="utf-8",
    )


def scaffold_task(tasks_directory: Path, task_id: str, title: str) -> Path:
    """Create and validate a minimal task, publishing it atomically."""
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise AuthoringError("Invalid task id: use lowercase letters, numbers, and single hyphens")
    if not title.strip():
        raise AuthoringError("Task title must not be blank")
    root = tasks_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / task_id
    if target.exists():
        raise AuthoringError(f"Task directory already exists: {task_id}")
    staging_parent = Path(tempfile.mkdtemp(prefix=f".{task_id}-", dir=root))
    staging = staging_parent / task_id
    try:
        staging.mkdir()
        _write_template(staging, task_id, title.strip())
        report = validate_task(staging)
        if not report.valid:
            raise AuthoringError(
                "Generated task failed validation:\n  - " + "\n  - ".join(report.errors)
            )
        if target.exists():
            raise AuthoringError(f"Task directory already exists: {task_id}")
        try:
            os.rename(staging, target)
        except FileExistsError as exc:
            raise AuthoringError(f"Task directory already exists: {task_id}") from exc
        staging_parent.rmdir()
    except Exception:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
        raise
    return target


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuthoringError(f"Could not inspect {path.name}: {exc}") from exc


def lint_task(task_directory: Path) -> AuthoringReport:
    """Add author-facing completeness and reproducibility checks to validation."""
    validation = validate_task(task_directory)
    diagnostics: list[AuthoringDiagnostic] = []
    if not validation.valid or validation.task is None:
        return AuthoringReport(validation=validation, diagnostics=diagnostics)
    task = validation.task
    root = task_directory.resolve()
    prompt = _read_text(safe_join(root, task.description_file))
    if not prompt.strip():
        diagnostics.append(
            AuthoringDiagnostic("error", "empty-description", "Task description is empty.")
        )
    elif any(marker in prompt.casefold() for marker in PLACEHOLDER_MARKERS):
        diagnostics.append(
            AuthoringDiagnostic(
                "warning",
                "placeholder-description",
                "Task description still contains template placeholders.",
            )
        )
    patch = _read_text(safe_join(root, "reference/solution.patch"))
    if not patch.strip():
        diagnostics.append(
            AuthoringDiagnostic("error", "empty-reference", "Reference patch is empty.")
        )
    elif any(marker in patch.casefold() for marker in PLACEHOLDER_MARKERS):
        diagnostics.append(
            AuthoringDiagnostic(
                "warning",
                "placeholder-reference",
                "Reference patch still contains template placeholders.",
            )
        )
    test_files = sorted((root / "tests").glob("**/test_*.py"))
    if any(
        any(marker in _read_text(path).casefold() for marker in PLACEHOLDER_MARKERS)
        for path in test_files
    ):
        diagnostics.append(
            AuthoringDiagnostic(
                "warning",
                "placeholder-tests",
                "Test files still contain template placeholders.",
            )
        )
    total = validation.public_tests + validation.private_tests
    if task.expected.passing_tests_after != total:
        diagnostics.append(
            AuthoringDiagnostic(
                "error",
                "test-count-mismatch",
                "expected.passing_tests_after must equal discovered public and private tests "
                f"({total}).",
            )
        )
    if task.expected.failing_tests_before > task.expected.passing_tests_after:
        diagnostics.append(
            AuthoringDiagnostic(
                "error",
                "failure-count-conflict",
                "expected.failing_tests_before cannot exceed passing_tests_after.",
            )
        )
    try:
        command = split_command(task.execution.test_command)
    except RepoGymError as exc:
        diagnostics.append(AuthoringDiagnostic("error", "invalid-command", str(exc)))
    else:
        executable = Path(command[0]).name.casefold()
        if executable in {"sh", "bash", "cmd", "cmd.exe", "powershell", "pwsh"}:
            diagnostics.append(
                AuthoringDiagnostic(
                    "error",
                    "shell-command",
                    "Test commands must use direct argv execution, not a shell launcher.",
                )
            )
        if any(option == "-x" or option.startswith("--maxfail") for option in command[1:]):
            diagnostics.append(
                AuthoringDiagnostic(
                    "warning",
                    "incomplete-test-run",
                    "The configured test command may stop before collecting all failures.",
                )
            )
        for argument in command:
            if PurePosixPath(argument).is_absolute() or PureWindowsPath(argument).is_absolute():
                diagnostics.append(
                    AuthoringDiagnostic(
                        "warning",
                        "absolute-command-path",
                        "The configured test command contains a host-specific absolute path.",
                    )
                )
                break
    if task.constraints.allowed_paths == ["**"]:
        diagnostics.append(
            AuthoringDiagnostic(
                "warning",
                "unbounded-scope",
                "Allowed paths cover the entire submission; prefer a narrower scope.",
            )
        )
    diagnostics.sort(key=lambda item: (item.status, item.code, item.message))
    return AuthoringReport(validation=validation, diagnostics=diagnostics)
