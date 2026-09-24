from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from repogym.cli import app
from repogym.comparison import compare_runs, generate_comparison


def _write_run(
    root: Path,
    run_id: str,
    *,
    score: float,
    passed: int,
    duration: float,
    violations: list[str],
) -> Path:
    run = root / run_id
    run.mkdir()
    result = {
        "task_id": "sample-task",
        "run_id": run_id,
        "status": "completed",
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
    assert comparison.tests_passed.delta == 3
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
    assert "tests passed" in output.export_text()


def test_compare_cli_supports_json(tmp_path: Path) -> None:
    run_a = _write_run(tmp_path, "run-a", score=10, passed=1, duration=2, violations=[])
    run_b = _write_run(tmp_path, "run-b", score=20, passed=2, duration=1, violations=[])
    result = CliRunner().invoke(app, ["compare", str(run_a), str(run_b), "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["tests_passed"]["delta"] == 1
