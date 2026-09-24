"""Local subprocess executor. This is not a security sandbox."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import psutil

from repogym.models import ExecutionResult


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
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        started = time.monotonic()
        environment = os.environ.copy()
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
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds)
            return ExecutionResult(
                command=command,
                return_code=process.returncode,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired as timeout:
            diagnostics = _terminate_process_tree(root_process)
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=2)
            except subprocess.TimeoutExpired as cleanup_timeout:
                diagnostics.append("Process pipes remained open after tree termination.")
                try:
                    process.kill()
                except OSError as exc:
                    diagnostics.append(f"Could not kill root process {process.pid}: {exc}")
                stdout_bytes = cleanup_timeout.stdout or timeout.stdout or b""
                stderr_bytes = cleanup_timeout.stderr or timeout.stderr or b""
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            if diagnostics:
                separator = "\n" if stderr and not stderr.endswith("\n") else ""
                stderr += separator + "\n".join(diagnostics)
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr,
                duration_seconds=time.monotonic() - started,
                timed_out=True,
                termination_diagnostics=diagnostics,
            )
        except OSError as exc:
            return ExecutionResult(
                command=command,
                return_code=None,
                stdout="",
                stderr=str(exc),
                duration_seconds=time.monotonic() - started,
            )
