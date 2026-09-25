"""CI smoke workflow that honors RepoGym's public exit-code contract."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from repogym.exit_codes import ExitCode

CommandRunner = Callable[[list[str]], int]


class SmokeError(RuntimeError):
    """Raised when a smoke-test command violates its expected outcome."""


def _execute(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def _expect(command: list[str], expected: ExitCode, execute: CommandRunner) -> None:
    actual = execute(command)
    if actual != expected:
        rendered = " ".join(command)
        raise SmokeError(f"{rendered} returned {actual}; expected {int(expected)}")


def run_smoke(runs_root: Path, execute: CommandRunner = _execute) -> None:
    """Create one incomplete and one perfect run, then compare both formats."""
    before = set(runs_root.iterdir()) if runs_root.is_dir() else set()
    repogym = [sys.executable, "-m", "repogym.cli"]
    task = "tasks/python-cache-ttl"
    _expect(
        [
            *repogym,
            "grade",
            task,
            "--submission",
            "examples/submissions/cache-ttl-broken",
        ],
        ExitCode.SCORE_NOT_PASSED,
        execute,
    )
    _expect(
        [
            *repogym,
            "grade",
            task,
            "--submission",
            "examples/submissions/cache-ttl-fixed",
        ],
        ExitCode.SUCCESS,
        execute,
    )
    after = set(runs_root.iterdir()) if runs_root.is_dir() else set()
    created = sorted(path for path in after - before if path.is_dir())
    if len(created) != 2:
        raise SmokeError(f"Expected two new run directories, found {len(created)}")
    run_a, run_b = map(str, created)
    _expect([*repogym, "compare", run_a, run_b], ExitCode.SUCCESS, execute)
    _expect(
        [
            *repogym,
            "compare",
            run_a,
            run_b,
            "--format",
            "json",
            "--output",
            ".repogym/comparison.json",
        ],
        ExitCode.SUCCESS,
        execute,
    )


def main() -> int:
    try:
        run_smoke(Path(".repogym/runs"))
    except SmokeError as exc:
        print(f"comparison smoke test failed: {exc}", file=sys.stderr)
        return 1
    return 0
