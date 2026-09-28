"""Executor protocol."""

from pathlib import Path
from threading import Event
from typing import Protocol

from repogym.models import ExecutionResult, ExecutorCapabilities, ExecutorPolicyEvidence


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
    def capabilities(self) -> ExecutorCapabilities: ...

    def policy(self) -> ExecutorPolicyEvidence: ...

    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult: ...


def executor_capabilities(executor: object) -> ExecutorCapabilities:
    method = getattr(executor, "capabilities", None)
    if callable(method):
        result = method()
        if isinstance(result, ExecutorCapabilities):
            return result
    name = f"{type(executor).__module__}.{type(executor).__qualname__}"
    return ExecutorCapabilities(
        backend=name,
        available=True,
        availability_reason="Custom executor did not declare capabilities.",
        filesystem_isolation=False,
        network_control=False,
        cpu_limit=False,
        memory_limit=False,
        process_limit=False,
    )


def executor_policy(executor: object) -> ExecutorPolicyEvidence:
    method = getattr(executor, "policy", None)
    if callable(method):
        result = method()
        if isinstance(result, ExecutorPolicyEvidence):
            return result
    name = f"{type(executor).__module__}.{type(executor).__qualname__}"
    return ExecutorPolicyEvidence(
        backend=name,
        filesystem_mode="unknown",
        network_mode="unknown",
    )
