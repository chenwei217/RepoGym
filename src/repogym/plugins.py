"""Versioned extension contracts and isolated entry-point discovery."""

from __future__ import annotations

import importlib.metadata
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol, runtime_checkable

from repogym.exceptions import PluginError, TaskLoadError
from repogym.executors.base import CancellationToken
from repogym.loader import task_from_mapping
from repogym.models import ExecutionResult, GradeResult, TaskSpec
from repogym.security import redact_sensitive_text, redact_value

PLUGIN_API_VERSION = 1
PLUGIN_ENTRY_POINT_GROUP = "repogym.plugins"
_PLUGIN_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class PluginTaskLoadRequest:
    """Stable input supplied to a task-loader extension."""

    task_directory: Path


@dataclass(frozen=True)
class PluginExecutionRequest:
    """Stable execution input independent of RepoGym's internal result model."""

    argv: tuple[str, ...]
    working_directory: Path
    timeout_seconds: int
    cancellation: CancellationSignal | None = None


@dataclass(frozen=True)
class PluginExecutionResponse:
    """Stable execution output converted to the internal result at the boundary."""

    return_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False
    termination_diagnostics: tuple[str, ...] = ()
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def __post_init__(self) -> None:
        if self.return_code is not None and (
            not isinstance(self.return_code, int) or isinstance(self.return_code, bool)
        ):
            raise ValueError("return_code must be an integer or None")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise ValueError("stdout and stderr must be text")
        if (
            not isinstance(self.duration_seconds, (int, float))
            or isinstance(self.duration_seconds, bool)
            or self.duration_seconds < 0
        ):
            raise ValueError("duration_seconds must be non-negative")
        for name in ("timed_out", "cancelled", "stdout_truncated", "stderr_truncated"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if self.timed_out and self.cancelled:
            raise ValueError("an execution cannot be timed out and cancelled")
        if not isinstance(self.termination_diagnostics, tuple) or not all(
            isinstance(item, str) for item in self.termination_diagnostics
        ):
            raise ValueError("termination_diagnostics must be a tuple of text values")
        for name in ("stdout_bytes", "stderr_bytes"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class PluginReportRequest:
    """Sanitized, serialization-shaped input supplied to a report extension."""

    result: Mapping[str, Any]
    stdout: str
    stderr: str


@runtime_checkable
class CancellationSignal(Protocol):
    """Read-only cancellation surface available to executor extensions."""

    @property
    def cancelled(self) -> bool: ...


@runtime_checkable
class TaskLoaderPlugin(Protocol):
    def load_task(self, request: PluginTaskLoadRequest) -> Mapping[str, Any]: ...


@runtime_checkable
class ExecutorBackendPlugin(Protocol):
    def execute(self, request: PluginExecutionRequest) -> PluginExecutionResponse: ...


@runtime_checkable
class ReporterPlugin(Protocol):
    def render(self, request: PluginReportRequest) -> str: ...


@dataclass(frozen=True)
class PluginRegistration:
    """One versioned entry-point registration with one or more extension roles."""

    name: str
    api_version: int
    task_loader: TaskLoaderPlugin | None = None
    executor: ExecutorBackendPlugin | None = None
    reporter: ReporterPlugin | None = None


PluginStatus = Literal["loaded", "failed", "incompatible", "conflict"]


@dataclass(frozen=True)
class PluginDiagnostic:
    entry_point: str
    status: PluginStatus
    message: str


@dataclass(frozen=True)
class PluginRegistry:
    """Immutable discovery result; rejected plugins remain observable as diagnostics."""

    plugins: Mapping[str, PluginRegistration]
    diagnostics: tuple[PluginDiagnostic, ...]

    def get(self, name: str) -> PluginRegistration:
        try:
            return self.plugins[name]
        except KeyError as exc:
            raise PluginError(f"Plugin is not available: {name}") from exc


class _EntryPoint(Protocol):
    name: str
    value: str

    def load(self) -> object: ...


def _diagnostic(entry_point: _EntryPoint, status: PluginStatus, message: str) -> PluginDiagnostic:
    source = f"{entry_point.name} = {entry_point.value}"
    return PluginDiagnostic(source, status, redact_sensitive_text(message))


def _validate_registration(value: object) -> str | None:
    if not isinstance(value, PluginRegistration):
        return "entry point must load a PluginRegistration"
    if not _PLUGIN_NAME.fullmatch(value.name):
        return "plugin name must use lowercase letters, digits, and single hyphens"
    if not isinstance(value.api_version, int) or isinstance(value.api_version, bool):
        return "plugin API version must be an integer"
    if value.api_version != PLUGIN_API_VERSION:
        return None
    extensions = (value.task_loader, value.executor, value.reporter)
    if all(extension is None for extension in extensions):
        return "registration must provide at least one extension"
    checks = (
        (value.task_loader, TaskLoaderPlugin, "task loader"),
        (value.executor, ExecutorBackendPlugin, "executor"),
        (value.reporter, ReporterPlugin, "reporter"),
    )
    for extension, protocol, label in checks:
        if extension is not None and not isinstance(extension, protocol):
            return f"{label} does not implement its protocol"
    return None


def discover_plugins(entry_points: Iterable[_EntryPoint] | None = None) -> PluginRegistry:
    """Discover plugins deterministically without allowing one failure to abort discovery."""
    diagnostics: list[PluginDiagnostic] = []
    if entry_points is None:
        try:
            entry_points = importlib.metadata.entry_points().select(group=PLUGIN_ENTRY_POINT_GROUP)
        except Exception as exc:
            message = redact_sensitive_text(str(exc))
            diagnostic = PluginDiagnostic(PLUGIN_ENTRY_POINT_GROUP, "failed", message)
            return PluginRegistry(MappingProxyType({}), (diagnostic,))

    loaded: dict[str, PluginRegistration] = {}
    ordered = sorted(entry_points, key=lambda item: (item.name.casefold(), item.value))
    for entry_point in ordered:
        try:
            value = entry_point.load()
        except Exception as exc:
            diagnostics.append(_diagnostic(entry_point, "failed", f"load failed: {exc}"))
            continue
        try:
            error = _validate_registration(value)
        except Exception as exc:
            diagnostics.append(
                _diagnostic(entry_point, "failed", f"registration validation failed: {exc}")
            )
            continue
        if not isinstance(value, PluginRegistration):
            diagnostics.append(_diagnostic(entry_point, "failed", error or "invalid registration"))
            continue
        if not isinstance(value.api_version, int) or isinstance(value.api_version, bool):
            diagnostics.append(_diagnostic(entry_point, "failed", error or "invalid API version"))
            continue
        if value.api_version != PLUGIN_API_VERSION:
            diagnostics.append(
                _diagnostic(
                    entry_point,
                    "incompatible",
                    f"API version {value.api_version}; required {PLUGIN_API_VERSION}",
                )
            )
            continue
        if error is not None:
            diagnostics.append(_diagnostic(entry_point, "failed", error))
            continue
        if value.name in loaded:
            diagnostics.append(
                _diagnostic(entry_point, "conflict", f"duplicate plugin name: {value.name}")
            )
            continue
        loaded[value.name] = value
        roles = [
            label
            for extension, label in (
                (value.task_loader, "task-loader"),
                (value.executor, "executor"),
                (value.reporter, "reporter"),
            )
            if extension is not None
        ]
        diagnostics.append(_diagnostic(entry_point, "loaded", ", ".join(roles)))
    return PluginRegistry(MappingProxyType(dict(sorted(loaded.items()))), tuple(diagnostics))


def load_task_with_plugin(registration: PluginRegistration, task_directory: Path) -> TaskSpec:
    """Invoke a registered loader and validate its mapping through the core schema pipeline."""
    if registration.task_loader is None:
        raise PluginError(f"Plugin {registration.name!r} does not provide a task loader")
    task_dir = task_directory.resolve()
    try:
        raw = registration.task_loader.load_task(PluginTaskLoadRequest(task_dir))
        return task_from_mapping(raw, task_dir)
    except TaskLoadError:
        raise
    except Exception as exc:
        message = redact_sensitive_text(str(exc), [task_dir])
        raise PluginError(f"Task loader {registration.name!r} failed: {message}") from exc


class PluginExecutorAdapter:
    """Adapt a registered executor extension to RepoGym's internal Executor protocol."""

    def __init__(self, registration: PluginRegistration) -> None:
        if registration.executor is None:
            raise PluginError(f"Plugin {registration.name!r} does not provide an executor")
        self.name = registration.name
        self._backend = registration.executor

    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        request = PluginExecutionRequest(
            argv=tuple(command),
            working_directory=cwd.resolve(),
            timeout_seconds=timeout_seconds,
            cancellation=cancellation_token,
        )
        try:
            response = self._backend.execute(request)
        except Exception as exc:
            message = redact_sensitive_text(str(exc), [cwd.resolve()])
            raise PluginError(f"Executor plugin {self.name!r} failed: {message}") from exc
        if not isinstance(response, PluginExecutionResponse):
            raise PluginError(f"Executor plugin {self.name!r} returned an invalid response type")
        stdout_bytes = response.stdout_bytes
        stderr_bytes = response.stderr_bytes
        return ExecutionResult(
            command=command,
            return_code=response.return_code,
            stdout=response.stdout,
            stderr=response.stderr,
            duration_seconds=response.duration_seconds,
            timed_out=response.timed_out,
            cancelled=response.cancelled,
            termination_diagnostics=list(response.termination_diagnostics),
            stdout_bytes=(
                len(response.stdout.encode("utf-8")) if stdout_bytes is None else stdout_bytes
            ),
            stderr_bytes=(
                len(response.stderr.encode("utf-8")) if stderr_bytes is None else stderr_bytes
            ),
            stdout_truncated=response.stdout_truncated,
            stderr_truncated=response.stderr_truncated,
        )


def render_with_plugin(
    registration: PluginRegistration,
    result: GradeResult,
    stdout: str,
    stderr: str,
    sensitive_roots: Iterable[Path] = (),
) -> str:
    """Render with a plugin while preserving RepoGym's redaction boundary."""
    if registration.reporter is None:
        raise PluginError(f"Plugin {registration.name!r} does not provide a reporter")
    roots = tuple(path.resolve() for path in sensitive_roots)
    request = PluginReportRequest(
        result=redact_value(result.model_dump(mode="json"), roots),
        stdout=redact_sensitive_text(stdout, roots),
        stderr=redact_sensitive_text(stderr, roots),
    )
    try:
        rendered = registration.reporter.render(request)
    except Exception as exc:
        message = redact_sensitive_text(str(exc), roots)
        raise PluginError(f"Reporter plugin {registration.name!r} failed: {message}") from exc
    if not isinstance(rendered, str):
        raise PluginError(f"Reporter plugin {registration.name!r} returned a non-text result")
    return redact_sensitive_text(rendered, roots)
