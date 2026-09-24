from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from repogym.cli import app
from repogym.comparison import compare_runs, generate_comparison
from repogym.exceptions import ReportError


def _write_run(
    root: Path,
    run_id: str,
    *,
    score: float,
    passed: int,
    duration: float,
    violations: list[str],
    task_id: str = "sample-task",
    fingerprint: str | None = "a" * 64,
    status: str = "completed",
    timed_out: bool = False,
) -> Path:
    run = root / run_id
    run.mkdir()
    result = {
        "task_id": task_id,
        "task_fingerprint": fingerprint,
        "run_id": run_id,
        "status": status,
        "score": score,
        "dimensions": {
            "correctness": {
                "score": score * 0.6,
                "max_score": 60,
                "reason": "fixture",
            },
            "scope_control": {"score": 10, "max_score": 10, "reason": "fixture"},
        },
        "tests": {"passed": passed, "failed": 8 - passed, "total": 8},
        "violations": violations,
        "duration_seconds": duration,
        "execution": {
            "argv": ["python", "-m", "pytest"],
            "exit_code": None if timed_out else 0,
            "timed_out": timed_out,
            "duration_seconds": duration,
            "working_directory": "<WORKSPACE>",
            "stdout_file": "stdout.txt",
            "stderr_file": "stderr.txt",
            "test_statistics_source": "pytest_summary",
        },
    }
    (run / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run / "stdout.txt").write_text("", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    return run


def test_compare_runs_covers_scores_tests_duration_and_violations(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=50, passed=4, duration=2.5, violations=["old"])
    run_b = _write_run(tmp_path, "run-b", score=80, passed=7, duration=1.25, violations=["new"])
    comparison = compare_runs(run_a, run_b)
    assert comparison.score.delta == 30
    assert comparison.dimensions["correctness"].delta == 18
    assert comparison.tests.passed.delta == 3
    assert comparison.tests.failed.delta == -3
    assert comparison.tests.total.delta == 0
    assert comparison.duration_seconds.delta == -1.25
    assert comparison.violations_added == ["new"]
    assert comparison.violations_removed == ["old"]


def test_comparison_terminal_and_json_are_deterministic(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=40, passed=3, duration=2, violations=[])
    run_b = _write_run(tmp_path, "run-b", score=60, passed=5, duration=3, violations=[])
    first = generate_comparison(run_a, run_b, "json")
    second = generate_comparison(run_a, run_b, "json")
    assert first == second
    assert first is not None and json.loads(first)["score"]["delta"] == 20
    output = Console(record=True, width=120)
    assert generate_comparison(run_a, run_b, "terminal", output) is None
    terminal = output.export_text()
    assert "tests passed" in terminal
    assert "Status: completed -> completed" in terminal


def test_compare_cli_supports_json(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=10, passed=1, duration=2, violations=[])
    run_b = _write_run(tmp_path, "run-b", score=20, passed=2, duration=1, violations=[])
    result = CliRunner().invoke(app, ["compare", str(run_a), str(run_b), "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["tests"]["passed"]["delta"] == 1


def test_compare_rejects_different_task_ids(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=10, passed=1, duration=2, violations=[])
    run_b = _write_run(
        tmp_path,
        "run-b",
        score=20,
        passed=2,
        duration=1,
        violations=[],
        task_id="other-task",
    )
    with pytest.raises(ReportError, match="different tasks"):
        compare_runs(run_a, run_b)


def test_compare_warns_on_fingerprint_mismatch_and_compares_timeout(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=10, passed=1, duration=2, violations=[])
    run_b = _write_run(
        tmp_path,
        "run-b",
        score=20,
        passed=2,
        duration=1,
        violations=[],
        fingerprint="b" * 64,
        status="timed_out",
        timed_out=True,
    )
    comparison = compare_runs(run_a, run_b)
    assert comparison.warnings == [
        "Task fingerprints differ; scores may represent different task versions."
    ]
    assert comparison.status.changed
    assert comparison.timed_out.run_b is True
    output = Console(record=True, width=120)
    generate_comparison(run_a, run_b, "terminal", output)
    assert "WARNING: Task fingerprints differ" in output.export_text()


@pytest.mark.parametrize("format_name", ["terminal", "json"])
def test_compare_cli_writes_output_file(tmp_path: Path, format_name: str) -> None:
    run_a = _write_run(tmp_path, "run-a", score=10, passed=1, duration=2, violations=[])
    run_b = _write_run(tmp_path, "run-b", score=20, passed=2, duration=1, violations=[])
    output = tmp_path / f"comparison.{format_name}"
    result = CliRunner().invoke(
        app,
        [
            "compare",
            str(run_a),
            str(run_b),
            "--format",
            format_name,
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert output.is_file()
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
