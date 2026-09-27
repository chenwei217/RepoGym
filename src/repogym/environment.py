"""Versioned, non-sensitive runtime environment snapshots."""

from __future__ import annotations

import platform
from importlib import metadata

from rich.console import Console
from rich.table import Table

from repogym import __version__
from repogym.executors.base import Executor
from repogym.executors.local import LocalExecutor
from repogym.models import RuntimeEnvironmentEvidence, RuntimeEnvironmentSnapshot

DEPENDENCY_DISTRIBUTIONS = (
    "Jinja2",
    "psutil",
    "pydantic",
    "PyYAML",
    "rich",
    "typer",
)


def executor_identity(executor: Executor) -> str:
    """Return a stable identity without paths, hostnames, or object representations."""
    if isinstance(executor, LocalExecutor):
        return f"local:stdout={executor.max_stdout_bytes}:stderr={executor.max_stderr_bytes}"
    return f"{type(executor).__module__}.{type(executor).__qualname__}"


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            value = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            value = "unavailable"
        versions[distribution.casefold()] = value
    return dict(sorted(versions.items()))


def environment_fingerprint(snapshot: RuntimeEnvironmentSnapshot) -> str:
    return snapshot.fingerprint()


def collect_runtime_environment(
    executor: Executor | None = None,
) -> RuntimeEnvironmentEvidence:
    """Collect deterministic runtime facts that exclude local identity and paths."""
    runner = executor or LocalExecutor()
    snapshot = RuntimeEnvironmentSnapshot(
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        operating_system=platform.system().lower() or "unknown",
        operating_system_release=platform.release() or "unknown",
        architecture=platform.machine().lower() or "unknown",
        dependencies=_dependency_versions(),
        repogym_version=__version__,
        executor=executor_identity(runner),
    )
    return RuntimeEnvironmentEvidence(
        availability="available",
        fingerprint=environment_fingerprint(snapshot),
        snapshot=snapshot,
        reason="collected",
    )


def render_environment_terminal(
    environment: RuntimeEnvironmentEvidence,
    console: Console,
) -> None:
    if environment.availability != "available" or environment.snapshot is None:
        console.print(f"Runtime environment unavailable ({environment.reason})")
        return
    snapshot = environment.snapshot
    table = Table("Component", "Version / identity")
    table.add_row(
        "Python",
        f"{snapshot.python_implementation} {snapshot.python_version}",
    )
    table.add_row(
        "Operating system",
        f"{snapshot.operating_system} {snapshot.operating_system_release} "
        f"({snapshot.architecture})",
    )
    table.add_row("RepoGym", snapshot.repogym_version)
    table.add_row("Executor", snapshot.executor)
    for name, version in snapshot.dependencies.items():
        table.add_row(name, version)
    console.print(table)
    console.print(f"Environment fingerprint: {environment.fingerprint}")
