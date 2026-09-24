"""Local subprocess executor. This is not a security sandbox."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from repogym.models import ExecutionResult


class LocalExecutor:
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        started = time.monotonic()
        environment = os.environ.copy()
        for name in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE"):
            environment.pop(name, None)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                check=False,
                env=environment,
                shell=False,
                timeout=timeout_seconds,
            )
            return ExecutionResult(
                command=command,
                return_code=completed.returncode,
                stdout=completed.stdout.decode("utf-8", errors="replace"),
                stderr=completed.stderr.decode("utf-8", errors="replace"),
                duration_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=time.monotonic() - started,
                timed_out=True,
            )
        except OSError as exc:
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout="",
                stderr=str(exc),
                duration_seconds=time.monotonic() - started,
            )
