from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repogym.cli import app
from repogym.doctor import diagnose_task
from repogym.loader import load_task
from repogym.models import ExecutionResult
from repogym.testing import run_tests


class RecordingExecutor:
    def __init__(self) -> None:
        self.command: list[str] = []

    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        self.command = command
        return ExecutionResult(
            command=command,
            return_code=0,
            stdout="1 passed",
            stderr="",
            duration_seconds=0.1,
        )


def test_doctor_reports_healthy_environment(valid_task: Path) -> None:
    report = diagnose_task(valid_task)
    assert report.healthy
    assert {check.name for check in report.checks} >= {
        "python version",
        "test command",
        "dependencies",
        "working directory",
        "starter project",
        "public test discovery",
        "private test discovery",
        "temporary directory",
        "task fingerprint",
    }
    assert all(check.status == "pass" for check in report.checks)


def test_doctor_reports_the_same_interpreter_used_for_execution(
    valid_task: Path, tmp_path: Path
) -> None:
    report = diagnose_task(valid_task)
    command_check = next(check for check in report.checks if check.name == "test command")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executor = RecordingExecutor()

    run_tests(load_task(valid_task), workspace, executor)

    assert executor.command[0] == sys.executable
    assert command_check.status == "pass"
    assert sys.executable in command_check.message


def test_doctor_reports_missing_executable(valid_task: Path) -> None:
    config = valid_task / "task.yaml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("python -m pytest -q", "repogym-command-that-does-not-exist"),
        encoding="utf-8",
    )
    report = diagnose_task(valid_task)
    assert not report.healthy
    command = next(check for check in report.checks if check.name == "test command")
    assert command.status == "fail"
    assert "not found" in command.message
    dependencies = next(check for check in report.checks if check.name == "dependencies")
    assert dependencies.status == "warning"


def test_doctor_reports_invalid_task(tmp_path: Path) -> None:
    report = diagnose_task(tmp_path / "missing")
    assert not report.healthy
    assert report.checks[0].name == "task definition"
    assert report.checks[0].status == "fail"


def test_doctor_reports_invalid_yaml(valid_task: Path) -> None:
    (valid_task / "task.yaml").write_text("execution: [invalid\n", encoding="utf-8")
    report = diagnose_task(valid_task)
    assert not report.healthy
    assert "Could not read task.yaml" in report.checks[0].message


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_doctor_reports_missing_tests(valid_task: Path, visibility: str) -> None:
    test_file = valid_task / "tests" / visibility / f"test_{visibility}.py"
    test_file.unlink()
    report = diagnose_task(valid_task)
    discovery = next(
        check for check in report.checks if check.name == f"{visibility} test discovery"
    )
    assert not report.healthy
    assert discovery.status == "fail"
    assert discovery.message.startswith("0 ")


def test_doctor_reports_unsafe_working_directory(valid_task: Path) -> None:
    config = valid_task / "task.yaml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace('working_directory: "."', 'working_directory: "../outside"'),
        encoding="utf-8",
    )
    report = diagnose_task(valid_task)
    working = next(check for check in report.checks if check.name == "working directory")
    assert not report.healthy
    assert working.status == "fail"


def test_doctor_reports_unparseable_test_command(valid_task: Path) -> None:
    config = valid_task / "task.yaml"
    text = config.read_text(encoding="utf-8")
    config.write_text(text.replace("python -m pytest -q", "python -m 'pytest"), encoding="utf-8")
    report = diagnose_task(valid_task)
    command = next(check for check in report.checks if check.name == "test command")
    assert not report.healthy
    assert command.status == "fail"
    assert "Invalid test command" in command.message


def test_doctor_reports_unwritable_temporary_directory(
    valid_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_temporary_directory(*args: object, **kwargs: object) -> None:
        raise OSError("temporary storage unavailable")

    monkeypatch.setattr("repogym.doctor.tempfile.TemporaryDirectory", fail_temporary_directory)
    report = diagnose_task(valid_task)
    temporary = next(check for check in report.checks if check.name == "temporary directory")
    assert not report.healthy
    assert temporary.status == "fail"
    assert "unavailable" in temporary.message


def test_doctor_cli_normal_and_failure_paths(valid_task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    healthy = runner.invoke(app, ["doctor", str(valid_task)])
    assert healthy.exit_code == 0
    assert "PASS python version" in healthy.stdout
    assert Path(sys.executable).name in healthy.stdout
    failed = runner.invoke(app, ["doctor", str(tmp_path / "missing")])
    assert failed.exit_code == 1
    assert "FAIL task definition" in failed.stdout
