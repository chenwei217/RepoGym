from __future__ import annotations

from pathlib import Path

import pytest

from repogym.ci_smoke import SmokeError, run_smoke
from repogym.exit_codes import ExitCode


def test_comparison_smoke_accepts_expected_score_code(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    calls: list[list[str]] = []

    def execute(command: list[str]) -> int:
        calls.append(command)
        if "grade" in command:
            runs.mkdir(exist_ok=True)
            submission = command[-1]
            (runs / Path(submission).name).mkdir()
            return ExitCode.SCORE_NOT_PASSED if submission.endswith("broken") else ExitCode.SUCCESS
        return ExitCode.SUCCESS

    run_smoke(runs, execute)

    assert [command[3] for command in calls] == ["grade", "grade", "compare", "compare"]
    assert calls[-1][-2:] == ["--output", ".repogym/comparison.json"]


def test_comparison_smoke_rejects_unexpected_grade_code(tmp_path: Path) -> None:
    with pytest.raises(SmokeError, match="expected 30"):
        run_smoke(tmp_path / "runs", lambda _command: ExitCode.EXECUTION_FAILED)
