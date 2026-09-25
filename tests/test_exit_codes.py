from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import repogym.cli as cli_module
from repogym.cli import app
from repogym.exceptions import ExecutionError, ValidationError
from repogym.exit_codes import ExitCode
from repogym.models import GradeResult
from repogym.models import TestCounts as Counts


def _result(status: str, score: float) -> GradeResult:
    return GradeResult.model_validate(
        {
            "task_id": "exit-contract",
            "run_id": "run-1",
            "status": status,
            "score": score,
            "dimensions": {},
            "tests": Counts().model_dump(),
            "violations": [],
            "duration_seconds": 0,
        }
    )


def test_public_exit_code_values_are_stable() -> None:
    assert {name: int(code) for name, code in ExitCode.__members__.items()} == {
        "SUCCESS": 0,
        "TASK_INVALID": 10,
        "EXECUTION_FAILED": 20,
        "SCORE_NOT_PASSED": 30,
        "ENVIRONMENT_ERROR": 40,
        "INTERNAL_ERROR": 70,
    }


def test_invalid_task_and_environment_failures_use_distinct_codes(tmp_path: Path) -> None:
    runner = CliRunner()

    invalid = runner.invoke(app, ["validate", str(tmp_path / "missing")])
    diagnosed = runner.invoke(app, ["doctor", str(tmp_path / "missing")])
    listed = runner.invoke(app, ["list", "--tasks-dir", str(tmp_path / "missing")])

    assert invalid.exit_code == ExitCode.TASK_INVALID
    assert listed.exit_code == ExitCode.TASK_INVALID
    assert diagnosed.exit_code == ExitCode.ENVIRONMENT_ERROR


@pytest.mark.parametrize("format_name", ["terminal", "json", "junit", "sarif"])
def test_report_formats_share_environment_error_code(tmp_path: Path, format_name: str) -> None:
    result = CliRunner().invoke(
        app,
        ["report", str(tmp_path / "missing"), "--format", format_name],
    )

    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR


@pytest.mark.parametrize("format_name", ["terminal", "json"])
def test_comparison_formats_share_environment_error_code(tmp_path: Path, format_name: str) -> None:
    result = CliRunner().invoke(
        app,
        [
            "compare",
            str(tmp_path / "missing-a"),
            str(tmp_path / "missing-b"),
            "--format",
            format_name,
        ],
    )

    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR


@pytest.mark.parametrize(
    ("status", "score", "expected"),
    [
        ("completed", 100, ExitCode.SUCCESS),
        ("completed", 99, ExitCode.SCORE_NOT_PASSED),
        ("timed_out", 0, ExitCode.EXECUTION_FAILED),
        ("cancelled", 0, ExitCode.EXECUTION_FAILED),
        ("error", 0, ExitCode.EXECUTION_FAILED),
    ],
)
def test_grade_maps_persisted_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    score: float,
    expected: ExitCode,
) -> None:
    result = _result(status, score)
    monkeypatch.setattr(cli_module, "grade_submission", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(cli_module, "load_run", lambda _path: (result, "", ""))

    invoked = CliRunner().invoke(
        app,
        ["grade", "task", "--submission", "submission"],
    )

    assert invoked.exit_code == expected


def test_verify_distinguishes_task_and_execution_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()

    def execution_failure(_task: Path) -> None:
        raise ExecutionError("test process failed")

    monkeypatch.setattr(cli_module, "verify_task", execution_failure)
    executed = runner.invoke(app, ["verify", "task"])

    def task_failure(_task: Path) -> None:
        raise ValidationError("invalid task")

    monkeypatch.setattr(cli_module, "verify_task", task_failure)
    invalid = runner.invoke(app, ["verify", "task"])

    assert executed.exit_code == ExitCode.EXECUTION_FAILED
    assert invalid.exit_code == ExitCode.TASK_INVALID


def test_unexpected_exception_uses_internal_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_task: Path) -> None:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(cli_module, "validate_task", explode)
    result = CliRunner().invoke(app, ["validate", "task"])

    assert result.exit_code == ExitCode.INTERNAL_ERROR
    assert "unexpected failure" in result.stderr


def test_unhandled_filesystem_error_uses_environment_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_task: Path) -> None:
        raise OSError("filesystem unavailable")

    monkeypatch.setattr(cli_module, "validate_task", unavailable)
    result = CliRunner().invoke(app, ["validate", "task"])

    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert "filesystem unavailable" in result.stderr


def test_usage_errors_keep_framework_code() -> None:
    result = CliRunner().invoke(app, ["grade"])

    assert result.exit_code == 2


def test_cli_help_publishes_exit_code_contract() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == ExitCode.SUCCESS
    assert "10 invalid task/input" in result.stdout
    assert "70 internal error" in result.stdout
