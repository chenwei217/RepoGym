from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from repogym.cli import app
from repogym.exceptions import ReportError, SecurityError, ValidationError
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


@pytest.mark.parametrize("task_name", ["python-cache-ttl", "python-config-merge"])
def test_example_tasks_verify(task_name: str) -> None:
    report = verify_task(ROOT / "tasks" / task_name)
    assert report.fixed.return_code == 0
    assert report.patch_files


def test_verify_rejects_forbidden_reference_patch(valid_task: Path) -> None:
    patch = valid_task / "reference" / "solution.patch"
    patch.write_text(
        "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1 +1 @@\n-a\n+b\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="forbidden"):
        verify_task(valid_task)


def test_grades_correct_submission_and_writes_artifacts(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )
    result, stdout, stderr = load_run(run_dir)
    assert result.status == "completed"
    assert result.score == 100
    assert result.tests.passed == 8
    assert result.execution is not None
    assert result.execution.command == ["python", "-m", "pytest", "-q"]
    assert result.execution.exit_code == 0
    assert result.execution.timed_out is False
    assert result.execution.test_statistics_source == "pytest_summary"
    assert "8 passed" in stdout
    assert stderr == ""
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["task_fingerprint"]) == 64
    serialized_metadata = json.dumps(metadata)
    assert str(ROOT) not in serialized_metadata
    assert str(tmp_path) not in serialized_metadata
    assert set(path.name for path in run_dir.iterdir()) == {
        "changed_files.json",
        "metadata.json",
        "result.json",
        "stderr.txt",
        "stdout.txt",
    }


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
    assert result.tests.model_dump() == {"passed": 0, "failed": 8, "total": 8}
    assert (run_dir / "result.json").is_file()


def test_grade_rejects_missing_submission(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="does not exist"):
        grade_submission(ROOT / "tasks" / "python-cache-ttl", tmp_path / "missing")


def test_reports_render_all_formats_and_escape_html(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )
    (run_dir / "stdout.txt").write_text("<script>alert(1)</script>", encoding="utf-8")
    html_path = tmp_path / "report.html"
    html = generate_report(run_dir, "html", html_path)
    json_text = generate_report(run_dir, "json")
    terminal = Console(record=True, width=100)
    assert generate_report(run_dir, "terminal", console=terminal) is None
    assert html is not None and "&lt;script&gt;" in html and "<script>" not in html
    assert html_path.read_text(encoding="utf-8") == html
    assert json_text is not None and json.loads(json_text)["score"] == 100
    assert "correctness" in terminal.export_text()


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
