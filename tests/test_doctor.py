from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repogym.cli import app
from repogym.doctor import diagnose_task


def test_doctor_reports_healthy_environment(valid_task: Path) -> None:
    report = diagnose_task(valid_task)
    assert report.healthy
    assert {check.name for check in report.checks} >= {
        "python version",
        "test command",
        "dependencies",
        "working directory",
        "test discovery",
    }
    assert all(check.status == "pass" for check in report.checks)


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


def test_doctor_cli_normal_and_failure_paths(valid_task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    healthy = runner.invoke(app, ["doctor", str(valid_task)])
    assert healthy.exit_code == 0
    assert "PASS python version" in healthy.stdout
    failed = runner.invoke(app, ["doctor", str(tmp_path / "missing")])
    assert failed.exit_code == 1
    assert "FAIL task definition" in failed.stdout
