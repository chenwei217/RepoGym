"""Local subprocess executor. This is not a security sandbox."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import psutil

from repogym.executors.base import CancellationToken
from repogym.models import ExecutionResult, ExecutorCapabilities, ExecutorPolicyEvidence

DEFAULT_OUTPUT_LIMIT_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


@dataclass
class _BoundedCapture:
    limit: int
    total: int = 0
    head: bytearray = field(default_factory=bytearray)
    tail: bytearray = field(default_factory=bytearray)

    def add(self, chunk: bytes) -> None:
        self.total += len(chunk)
        head_limit = (self.limit + 1) // 2
        tail_limit = self.limit - head_limit
        if len(self.head) < head_limit:
            take = min(head_limit - len(self.head), len(chunk))
            self.head.extend(chunk[:take])
            chunk = chunk[take:]
        if tail_limit and chunk:
            self.tail.extend(chunk)
            if len(self.tail) > tail_limit:
                del self.tail[: len(self.tail) - tail_limit]

    @property
    def truncated(self) -> bool:
        return self.total > self.limit

    def text(self) -> str:
        head = bytes(self.head).decode("utf-8", errors="replace")
        tail = bytes(self.tail).decode("utf-8", errors="replace")
        if not self.truncated:
            return head + tail
        removed = self.total - self.limit
        return f"{head}\n... <{removed} bytes truncated> ...\n{tail}"


def _capture_pipe(stream: BinaryIO, capture: _BoundedCapture) -> None:
    try:
        while chunk := stream.read(_READ_CHUNK_BYTES):
            capture.add(chunk)
    except (OSError, ValueError):
        return


def _start_capture_threads(
    process: subprocess.Popen[bytes], stdout: _BoundedCapture, stderr: _BoundedCapture
) -> list[threading.Thread]:
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    if stdout_pipe is None or stderr_pipe is None:
        raise RuntimeError("executor process was created without captured output pipes")
    threads = [
        threading.Thread(target=_capture_pipe, args=(stdout_pipe, stdout), daemon=True),
        threading.Thread(target=_capture_pipe, args=(stderr_pipe, stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    return threads


def _finish_capture(process: subprocess.Popen[bytes], threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=2)
    if any(thread.is_alive() for thread in threads):
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        for thread in threads:
            thread.join(timeout=0.5)


def _wait_for_stop_reason(
    process: subprocess.Popen[bytes],
    timeout_seconds: int,
    cancellation_token: CancellationToken | None,
) -> str | None:
    deadline = time.monotonic() + timeout_seconds
    while process.poll() is None:
        if cancellation_token is not None and cancellation_token.cancelled:
            return "cancelled"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timed_out"
        interval = min(0.05, remaining)
        if cancellation_token is None:
            time.sleep(interval)
        else:
            cancellation_token.wait(interval)
    return None


def _terminate_process_tree(root: psutil.Process) -> list[str]:
    """Terminate only ``root`` and descendants captured from its process tree."""
    diagnostics: list[str] = []
    try:
        children = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return diagnostics
    except psutil.Error as exc:
        children = []
        diagnostics.append(f"Could not enumerate child processes: {exc}")

    targets = [*children, root]
    for process in targets:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            continue
        except (psutil.Error, OSError) as exc:
            diagnostics.append(f"Could not terminate process {process.pid}: {exc}")
    _, alive = psutil.wait_procs(targets, timeout=0.5)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            continue
        except (psutil.Error, OSError) as exc:
            diagnostics.append(f"Could not kill process {process.pid}: {exc}")
    _, survivors = psutil.wait_procs(alive, timeout=0.5)
    if survivors:
        diagnostics.append(
            "Processes still alive after timeout cleanup: "
            + ", ".join(str(process.pid) for process in survivors)
        )
    return diagnostics


class LocalExecutor:
    def __init__(
        self,
        max_stdout_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        max_stderr_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    ) -> None:
        if max_stdout_bytes < 1 or max_stderr_bytes < 1:
            raise ValueError("output limits must be positive")
        self.max_stdout_bytes = max_stdout_bytes
        self.max_stderr_bytes = max_stderr_bytes

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            backend="local",
            available=True,
            availability_reason="Local subprocess execution is available.",
            filesystem_isolation=False,
            network_control=False,
            cpu_limit=False,
            memory_limit=False,
            process_limit=False,
        )

    def policy(self) -> ExecutorPolicyEvidence:
        return ExecutorPolicyEvidence(
            backend="local",
            filesystem_mode="host",
            network_mode="host",
        )

    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        started = time.monotonic()
        if cancellation_token is not None and cancellation_token.cancelled:
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout="",
                stderr="",
                duration_seconds=time.monotonic() - started,
                cancelled=True,
            )
        environment = os.environ.copy()
        stdout_capture = _BoundedCapture(self.max_stdout_bytes)
        stderr_capture = _BoundedCapture(self.max_stderr_bytes)
        for name in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE"):
            environment.pop(name, None)
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                shell=False,
                start_new_session=os.name != "nt",
                creationflags=(
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
                ),
            )
            root_process = psutil.Process(process.pid)
            threads = _start_capture_threads(process, stdout_capture, stderr_capture)
            stop_reason = _wait_for_stop_reason(process, timeout_seconds, cancellation_token)
            diagnostics: list[str] = []
            if stop_reason is not None:
                diagnostics = _terminate_process_tree(root_process)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                diagnostics.append("Process pipes remained open after tree termination.")
                try:
                    process.kill()
                except OSError as exc:
                    diagnostics.append(f"Could not kill root process {process.pid}: {exc}")
            _finish_capture(process, threads)
            stderr = stderr_capture.text()
            if diagnostics:
                separator = "\n" if stderr and not stderr.endswith("\n") else ""
                stderr += separator + "\n".join(diagnostics)
            return ExecutionResult(
                command=command,
                return_code=process.returncode if stop_reason is None else None,
                stdout=stdout_capture.text(),
                stderr=stderr,
                duration_seconds=time.monotonic() - started,
                timed_out=stop_reason == "timed_out",
                cancelled=stop_reason == "cancelled",
                termination_diagnostics=diagnostics,
                stdout_bytes=stdout_capture.total,
                stderr_bytes=stderr_capture.total,
                stdout_truncated=stdout_capture.truncated,
                stderr_truncated=stderr_capture.truncated,
            )
        except OSError as exc:
            message = str(exc)
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout="",
                stderr=message,
                duration_seconds=time.monotonic() - started,
                stderr_bytes=len(message.encode("utf-8")),
            )
