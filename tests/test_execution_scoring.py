from __future__ import annotations

import sys
from pathlib import Path

from repogym.executors.local import LocalExecutor
from repogym.loader import load_task
from repogym.models import ExecutionResult
from repogym.models import TestCounts as Counts
from repogym.scoring import (
    path_matches,
    score_correctness,
    score_quality,
    score_regression,
    score_scope,
)
from repogym.testing import parse_test_counts


class FakeExecutor:
    def __init__(self, return_code: int = 0) -> None:
        self.return_code = return_code

    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        return ExecutionResult(
            command=command,
            return_code=self.return_code,
            stdout="",
            stderr="",
            duration_seconds=0.01,
        )


def test_local_executor_captures_output(tmp_path: Path) -> None:
    result = LocalExecutor().execute(
        [sys.executable, "-c", "print('hello')"], tmp_path, timeout_seconds=5
    )
    assert result.return_code == 0
    assert result.stdout.strip() == "hello"


def test_local_executor_times_out(tmp_path: Path) -> None:
    result = LocalExecutor().execute(
        [sys.executable, "-c", "import time; time.sleep(1)"], tmp_path, timeout_seconds=0.01
    )
    assert result.timed_out
    assert result.return_code is None


def test_local_executor_handles_missing_program(tmp_path: Path) -> None:
    result = LocalExecutor().execute(["definitely-not-a-real-program"], tmp_path, 1)
    assert result.return_code is None
    assert result.stderr


def test_parses_pytest_counts() -> None:
    result = ExecutionResult(
        command=["pytest"],
        return_code=1,
        stdout="5 passed, 2 failed, 1 error in 0.2s",
        stderr="",
        duration_seconds=0.2,
    )
    assert parse_test_counts(result) == Counts(passed=5, failed=3, total=8)


def test_scoring_formulas(valid_task: Path) -> None:
    task = load_task(valid_task)
    correctness = score_correctness(task, Counts(passed=3, failed=1, total=4))
    regression = score_regression(task, Counts(passed=1, failed=1, total=2))
    assert correctness.score == 45
    assert regression.score == 10


def test_scope_scoring(valid_task: Path) -> None:
    task = load_task(valid_task)
    clean, clean_violations = score_scope(task, ["src/answer.py"])
    bad, violations = score_scope(task, ["src/answer.py", "notes.txt"])
    forbidden, _ = score_scope(task, ["pyproject.toml"])
    assert clean.score == 10 and not clean_violations
    assert bad.score == 5 and violations
    assert forbidden.score == 0


def test_glob_matching() -> None:
    assert path_matches("src/nested/file.py", "src/**")
    assert path_matches("pyproject.toml", "pyproject.toml")
    assert not path_matches("docs/file.md", "src/**")


def test_quality_checks_syntax_and_lint(valid_task: Path, tmp_path: Path) -> None:
    task = load_task(valid_task)
    source = tmp_path / "src"
    source.mkdir()
    (source / "good.py").write_text("value = 1\n", encoding="utf-8")
    good = score_quality(task, tmp_path, ["src/good.py"], FakeExecutor(0))
    (source / "bad.py").write_text("if:\n", encoding="utf-8")
    bad = score_quality(task, tmp_path, ["src/bad.py"], FakeExecutor(1))
    unchanged = score_quality(task, tmp_path, [], FakeExecutor(1))
    assert good.score == 10
    assert bad.score == 0
    assert unchanged.score == 10
