"""Executor protocol."""

from pathlib import Path
from threading import Event
from typing import Protocol

from repogym.models import ExecutionResult


class CancellationToken:
    """Thread-safe, idempotent cooperative cancellation signal."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


class Executor(Protocol):
    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult: ...
