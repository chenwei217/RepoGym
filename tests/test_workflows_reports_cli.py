from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from repogym.cli import app
from repogym.exceptions import ReportError, SecurityError, ValidationError
from repogym.executors import CancellationToken
from repogym.grader import grade_submission
from repogym.models import ExecutionResult
from repogym.reports import generate_report, load_run
from repogym.verifier import verify_task

ROOT = Path(__file__).parents[1]


class TimeoutExecutor:
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        return ExecutionResult(
            command=command,
            return_code=None,
            stdout="",
            stderr="timed out",
            duration_seconds=0.01,
            timed_out=True,
        )


class NonzeroExecutor:
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        return ExecutionResult(
            command=command,
            return_code=3,
            stdout="1 failed in 0.01s",
            stderr="candidate failed",
            duration_seconds=0.01,
        )


class PathLeakingExecutor:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        local_path = str(cwd / "private" / "test_file.py")
        self.paths.append(str(cwd))
        return ExecutionResult(
            command=[str(cwd / "python")],
            return_code=0,
            stdout=f"8 passed at {local_path}",
            stderr=f"diagnostic from {local_path}",
            duration_seconds=0.01,
            termination_diagnostics=[f"cleanup checked {local_path}"],
        )


@pytest.mark.parametrize("task_name", ["python-cache-ttl", "python-config-merge"])
def test_example_tasks_verify(task_name: str) -> None:
    report = verify_task(ROOT / "tasks" / task_name)
    assert report.fixed.return_code == 0
    assert report.patch_files
    assert len(report.task_fingerprint) == 64


def test_verify_rejects_forbidden_reference_patch(valid_task: Path) -> None:
    patch = valid_task / "reference" / "solution.patch"
    patch.write_text(
        "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1 +1 @@\n-a\n+b\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="forbidden"):
        verify_task(valid_task)


def test_verify_honors_precancelled_token(valid_task: Path) -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ValidationError, match="cancelled"):
        verify_task(valid_task, cancellation_token=token)


def test_grades_correct_submission_and_writes_artifacts(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )
    result, stdout, stderr = load_run(run_dir)
    assert result.status == "completed"
    assert result.task_fingerprint == metadata_fingerprint(run_dir)
    assert result.score == 100
    assert result.tests.passed == 8
    assert result.execution is not None
    assert result.execution.argv == ["<ABSOLUTE_PATH>", "-m", "pytest", "-q"]
    assert result.execution.exit_code == 0
    assert result.execution.timed_out is False
    assert result.execution.duration_seconds >= 0
    assert result.execution.working_directory == "<WORKSPACE>"
    assert result.execution.stdout_file == "stdout.txt"
    assert result.execution.stderr_file == "stderr.txt"
    assert result.execution.test_statistics_source == "pytest_summary"
    assert result.execution.stdout_bytes > 0
    assert result.execution.stderr_bytes == 0
    assert result.execution.stdout_truncated is False
    assert result.execution.stderr_truncated is False
    assert "8 passed" in stdout
    assert stderr == ""
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["task_fingerprint"]) == 64
    assert metadata["execution"] == result.execution.model_dump(mode="json")
    serialized_metadata = json.dumps(metadata)
    assert str(ROOT) not in serialized_metadata
    assert str(tmp_path) not in serialized_metadata
    assert set(path.name for path in run_dir.iterdir()) == {
        "changed_files.json",
        "evidence.json",
        "metadata.json",
        "result.json",
        "stderr.txt",
        "stdout.txt",
    }


def test_grade_persists_cancelled_status_without_followup_commands(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
        cancellation_token=token,
    )
    result, stdout, stderr = load_run(run_dir)
    assert result.status == "cancelled"
    assert result.score == 0
    assert result.execution is not None
    assert result.execution.cancelled
    assert not result.execution.timed_out
    assert stdout == ""
    assert stderr == ""


def metadata_fingerprint(run_dir: Path) -> str:
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    value = metadata["task_fingerprint"]
    assert isinstance(value, str)
    return value


def test_bad_submission_loses_points(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-broken",
        tmp_path / "runs",
    )
    result, _, _ = load_run(run_dir)
    assert result.score < 100
    assert result.tests.failed > 0


def test_timeout_still_writes_result(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
        TimeoutExecutor(),
    )
    result, _, _ = load_run(run_dir)
    assert result.status == "timed_out"
    assert result.execution is not None
    assert result.execution.timed_out is True
    assert result.execution.exit_code is None
    assert result.tests.model_dump() == {"passed": 0, "failed": 8, "total": 8}
    assert (run_dir / "result.json").is_file()


def test_nonzero_exit_is_persisted_in_execution_evidence(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
        NonzeroExecutor(),
    )
    result, _, _ = load_run(run_dir)
    assert result.execution is not None
    assert result.execution.exit_code == 3
    assert result.execution.timed_out is False


def test_missing_test_command_writes_error_evidence(valid_task: Path, tmp_path: Path) -> None:
    config = valid_task / "task.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "python -m pytest -q", "definitely-not-a-real-program"
        ),
        encoding="utf-8",
    )
    submission = tmp_path / "submission"
    submission.mkdir()
    run_dir = grade_submission(valid_task, submission, tmp_path / "runs")
    result, _, stderr = load_run(run_dir)
    assert result.status == "error"
    assert result.execution is not None
    assert result.execution.argv == ["definitely-not-a-real-program"]
    assert result.execution.exit_code is None
    assert stderr


def test_grade_rejects_missing_submission(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="does not exist"):
        grade_submission(ROOT / "tasks" / "python-cache-ttl", tmp_path / "missing")


def test_reports_render_all_formats_and_escape_html(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )
    (run_dir / "stdout.txt").write_text(
        "<script>alert(1)</script> C:\\Users\\alice\\secret.py /home/alice/secret.py",
        encoding="utf-8",
    )
    html_path = tmp_path / "report.html"
    html = generate_report(run_dir, "html", html_path)
    json_text = generate_report(run_dir, "json")
    terminal = Console(record=True, width=100)
    assert generate_report(run_dir, "terminal", console=terminal) is None
    assert html is not None and "&lt;script&gt;" in html and "<script>" not in html
    assert "C:\\Users" not in html and "/home/alice" not in html
    assert html_path.read_text(encoding="utf-8") == html
    assert json_text is not None and json.loads(json_text)["score"] == 100
    assert "correctness" in terminal.export_text()


def test_grade_redacts_all_artifacts_and_does_not_capture_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "repogym-test-token-must-not-be-recorded"
    monkeypatch.setenv("REPOGYM_TEST_TOKEN", secret)
    executor = PathLeakingExecutor()
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
        executor,
    )
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(run_dir.iterdir()) if path.is_file()
    )
    assert secret not in artifact_text
    assert "<WORKSPACE>/private/test_file.py" in artifact_text
    assert all(path not in artifact_text for path in executor.paths)

    terminal = Console(record=True, width=120)
    generate_report(run_dir, "terminal", console=terminal)
    assert all(path not in terminal.export_text() for path in executor.paths)
    html = generate_report(run_dir, "html", tmp_path / "redacted.html")
    assert html is not None
    assert all(path not in html for path in executor.paths)


def test_report_rejects_incomplete_run(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="Invalid run directory"):
        load_run(tmp_path)


def test_cli_help_list_validate_and_version() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    listed = runner.invoke(app, ["list", "--tasks-dir", str(ROOT / "tasks")])
    assert listed.exit_code == 0
    assert "python-cache-ttl" in listed.stdout
    validated = runner.invoke(app, ["validate", str(ROOT / "tasks" / "python-cache-ttl")])
    assert validated.exit_code == 0
    assert "Validation passed" in validated.stdout
    versioned = runner.invoke(app, ["version"])
    assert versioned.exit_code == 0
    assert "0.1.0" in versioned.stdout


def test_cli_validation_failure_and_html_output_requirement(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid = runner.invoke(app, ["validate", str(tmp_path / "missing")])
    assert invalid.exit_code == 1
    report = runner.invoke(app, ["report", str(tmp_path), "--format", "html"])
    assert report.exit_code == 1
    assert "--output is required" in report.stderr
