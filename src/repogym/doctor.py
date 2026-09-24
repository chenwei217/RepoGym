"""Task execution environment diagnostics."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from repogym.commands import split_command
from repogym.exceptions import RepoGymError, SecurityError
from repogym.reproducibility import task_fingerprint
from repogym.security import safe_join
from repogym.validator import validate_task

DiagnosticStatus = Literal["pass", "warning", "fail"]


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: DiagnosticStatus
    message: str


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DiagnosticCheck]

    @property
    def healthy(self) -> bool:
        return all(check.status != "fail" for check in self.checks)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def diagnose_task(task_directory: Path) -> DoctorReport:
    """Inspect whether a task can run in the current local environment."""
    validation = validate_task(task_directory)
    checks: list[DiagnosticCheck] = []
    if validation.task is None:
        message = "; ".join(validation.errors)
        return DoctorReport([DiagnosticCheck("task definition", "fail", message)])
    task = validation.task
    if validation.errors:
        checks.append(DiagnosticCheck("task definition", "fail", "; ".join(validation.errors)))
    else:
        checks.append(DiagnosticCheck("task definition", "pass", f"Loaded {task.id}."))

    starter = task_directory.resolve() / "starter"
    starter_status: DiagnosticStatus = "pass" if starter.is_dir() else "fail"
    checks.append(
        DiagnosticCheck(
            "starter project",
            starter_status,
            "Starter project directory exists."
            if starter_status == "pass"
            else "Starter project directory is missing.",
        )
    )

    current = sys.version_info
    version = f"{current.major}.{current.minor}.{current.micro}"
    version_status: DiagnosticStatus = "pass" if current >= (3, 11) else "fail"
    checks.append(
        DiagnosticCheck("python version", version_status, f"Python {version}; requires 3.11+.")
    )

    try:
        command = split_command(task.execution.test_command)
    except RepoGymError as exc:
        checks.append(DiagnosticCheck("test command", "fail", str(exc)))
        command = []
    if command:
        executable = shutil.which(command[0])
        if executable is None:
            checks.append(
                DiagnosticCheck("test command", "fail", f"Executable not found: {command[0]}")
            )
        else:
            checks.append(
                DiagnosticCheck("test command", "pass", f"Executable found: {command[0]}")
            )

        if len(command) >= 3 and command[1] == "-m":
            module = command[2]
            module_status: DiagnosticStatus = "pass" if _module_available(module) else "fail"
            message = (
                f"Python module available: {module}"
                if module_status == "pass"
                else f"Python module not installed: {module}"
            )
            checks.append(DiagnosticCheck("dependencies", module_status, message))
        else:
            checks.append(
                DiagnosticCheck(
                    "dependencies",
                    "warning",
                    "Dependencies cannot be inferred from this test command.",
                )
            )

    try:
        working_directory = safe_join(
            task_directory.resolve() / "starter", task.execution.working_directory
        )
        exists = working_directory.is_dir()
    except SecurityError as exc:
        checks.append(DiagnosticCheck("working directory", "fail", str(exc)))
    else:
        status: DiagnosticStatus = "pass" if exists else "fail"
        message = (
            f"Starter working directory exists: {task.execution.working_directory}"
            if exists
            else f"Starter working directory is missing: {task.execution.working_directory}"
        )
        checks.append(DiagnosticCheck("working directory", status, message))

    for visibility, count in (
        ("public", validation.public_tests),
        ("private", validation.private_tests),
    ):
        discovery_status: DiagnosticStatus = "pass" if count else "fail"
        checks.append(
            DiagnosticCheck(
                f"{visibility} test discovery",
                discovery_status,
                f"{count} {visibility} tests found.",
            )
        )

    try:
        with tempfile.TemporaryDirectory(prefix="repogym-doctor-") as temporary:
            probe = Path(temporary) / "write-probe"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
    except OSError as exc:
        checks.append(DiagnosticCheck("temporary directory", "fail", str(exc)))
    else:
        checks.append(
            DiagnosticCheck("temporary directory", "pass", "Temporary workspace is writable.")
        )

    try:
        fingerprint = task_fingerprint(task_directory, task)
    except RepoGymError as exc:
        checks.append(DiagnosticCheck("task fingerprint", "fail", str(exc)))
    else:
        checks.append(
            DiagnosticCheck(
                "task fingerprint",
                "pass",
                f"Deterministic SHA-256: {fingerprint}",
            )
        )
    return DoctorReport(checks)
