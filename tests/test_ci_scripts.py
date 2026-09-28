from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from repogym.ci_smoke import SmokeError, run_smoke
from repogym.exit_codes import ExitCode

ROOT = Path(__file__).parents[1]
_BASH_BLOCK = re.compile(r"```bash\s*\n(?P<commands>.*?)```", re.DOTALL)


def _assert_checkout_path_matches(commands: str) -> None:
    lines = [line.strip() for line in commands.splitlines() if line.strip()]
    clone_index = next(
        (index for index, line in enumerate(lines) if line.startswith("git clone ")),
        None,
    )
    if clone_index is None:
        raise AssertionError("Quick Start must contain a git clone command")
    clone = shlex.split(lines[clone_index], posix=True)
    if len(clone) not in {3, 4}:
        raise AssertionError("git clone must use a URL and optional target directory")
    if clone_index + 1 >= len(lines):
        raise AssertionError("git clone must be followed by cd")
    change_directory = shlex.split(lines[clone_index + 1], posix=True)
    if len(change_directory) != 2 or change_directory[0] != "cd":
        raise AssertionError("git clone must be followed by cd")
    default_directory = Path(clone[2].removesuffix("/").removesuffix(".git")).name
    checkout_directory = clone[3] if len(clone) == 4 else default_directory
    if change_directory[1] != checkout_directory:
        raise AssertionError(
            "checkout directory mismatch: "
            f"clone creates {checkout_directory!r}, cd uses {change_directory[1]!r}"
        )


def test_readme_quick_start_uses_exact_checkout_directory() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    blocks = [match.group("commands") for match in _BASH_BLOCK.finditer(quick_start)]
    clone_block = next(block for block in blocks if "git clone " in block)
    _assert_checkout_path_matches(clone_block)


def test_checkout_path_check_rejects_case_mismatch() -> None:
    commands = "git clone https://example.test/Owner/RepoGym.git\ncd repogym\n"
    with pytest.raises(AssertionError, match="checkout directory mismatch"):
        _assert_checkout_path_matches(commands)


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
