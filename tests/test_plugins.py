from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from typer.testing import CliRunner

import repogym.cli as cli_module
import repogym.plugins as plugin_module
from repogym.cli import app
from repogym.exceptions import PluginError, TaskLoadError
from repogym.executors import CancellationToken
from repogym.loader import load_task
from repogym.models import GradeResult
from repogym.plugins import (
    PLUGIN_API_VERSION,
    PluginDiagnostic,
    PluginExecutionRequest,
    PluginExecutionResponse,
    PluginExecutorAdapter,
    PluginRegistration,
    PluginRegistry,
    PluginReportRequest,
    PluginTaskLoadRequest,
    discover_plugins,
    load_task_with_plugin,
    render_with_plugin,
)


@dataclass
class FakeEntryPoint:
    name: str
    value: str
    loaded: object
    error: Exception | None = None

    def load(self) -> object:
        if self.error is not None:
            raise self.error
        return self.loaded


class StaticLoader:
    def __init__(self, value: object) -> None:
        self.value = value
        self.request: PluginTaskLoadRequest | None = None

    def load_task(self, request: PluginTaskLoadRequest) -> Any:
        self.request = request
        return self.value


class EchoExecutor:
    def __init__(self) -> None:
        self.request: PluginExecutionRequest | None = None

    def execute(self, request: PluginExecutionRequest) -> PluginExecutionResponse:
        self.request = request
        return PluginExecutionResponse(
            return_code=0,
            stdout="done ✓",
            stderr="",
            duration_seconds=0.25,
        )


class SummaryReporter:
    def render(self, request: PluginReportRequest) -> str:
        return f"{request.result['task_id']}:{request.stdout}:{request.stderr}"


def _registration(name: str = "example", **overrides: object) -> PluginRegistration:
    values: dict[str, object] = {
        "name": name,
        "api_version": PLUGIN_API_VERSION,
        "reporter": SummaryReporter(),
    }
    values.update(overrides)
    return PluginRegistration(**values)  # type: ignore[arg-type]


def _grade_result() -> GradeResult:
    return GradeResult.model_validate(
        {
            "task_id": "plugin-task",
            "run_id": "run-1",
            "status": "completed",
            "score": 100,
            "dimensions": {},
            "tests": {"passed": 1, "failed": 0, "total": 1},
            "violations": [],
            "duration_seconds": 0.1,
        }
    )


def test_discovery_is_deterministic_and_records_loaded_roles() -> None:
    alpha = _registration("alpha")
    beta = _registration("beta", executor=EchoExecutor())
    registry = discover_plugins(
        [
            FakeEntryPoint("z", "package:beta", beta),
            FakeEntryPoint("a", "package:alpha", alpha),
        ]
    )

    assert list(registry.plugins) == ["alpha", "beta"]
    assert [item.entry_point for item in registry.diagnostics] == [
        "a = package:alpha",
        "z = package:beta",
    ]
    assert registry.diagnostics[1].message == "executor, reporter"
    assert registry.get("alpha") is alpha


def test_discovery_isolates_load_version_protocol_and_conflict_failures() -> None:
    winner = _registration("duplicate")
    entries = [
        FakeEntryPoint("broken", "bad:plugin", object(), RuntimeError("boom")),
        FakeEntryPoint("duplicate-a", "a:plugin", winner),
        FakeEntryPoint("duplicate-b", "b:plugin", _registration("duplicate")),
        FakeEntryPoint("empty", "empty:plugin", PluginRegistration("empty", 1)),
        FakeEntryPoint("future", "future:plugin", _registration("future", api_version=2)),
        FakeEntryPoint(
            "invalid-version", "invalid:version", _registration("invalid", api_version=True)
        ),
        FakeEntryPoint("shape", "shape:plugin", object()),
    ]

    registry = discover_plugins(reversed(entries))

    assert registry.plugins == {"duplicate": winner}
    assert [item.status for item in registry.diagnostics] == [
        "failed",
        "loaded",
        "conflict",
        "failed",
        "incompatible",
        "failed",
        "failed",
    ]
    assert "required 1" in registry.diagnostics[4].message
    assert "must be an integer" in registry.diagnostics[5].message
    with pytest.raises(PluginError, match="not available"):
        registry.get("missing")


def test_task_loader_adapter_migrates_and_validates_mapping(valid_task: Path) -> None:
    mapping = load_task(valid_task).model_dump(mode="python")
    mapping.pop("schema_version")
    loader = StaticLoader(MappingProxyType(mapping))
    registration = _registration("loader", task_loader=loader)

    task = load_task_with_plugin(registration, valid_task)

    assert task.schema_version == 1
    assert task.id == valid_task.name
    assert loader.request == PluginTaskLoadRequest(valid_task.resolve())


def test_task_loader_adapter_rejects_invalid_output_and_isolates_exceptions(
    valid_task: Path,
) -> None:
    invalid = _registration("invalid-loader", task_loader=StaticLoader(["not", "mapping"]))
    with pytest.raises(TaskLoadError, match="must return a mapping"):
        load_task_with_plugin(invalid, valid_task)

    class ExplodingLoader:
        def load_task(self, request: PluginTaskLoadRequest) -> Any:
            raise RuntimeError(f"cannot read {request.task_directory / 'secret.txt'}")

    exploding = _registration("exploding-loader", task_loader=ExplodingLoader())
    with pytest.raises(PluginError, match=r"cannot read <WORKSPACE>[/\\]secret.txt"):
        load_task_with_plugin(exploding, valid_task)

    with pytest.raises(PluginError, match="does not provide a task loader"):
        load_task_with_plugin(_registration(), valid_task)


def test_executor_adapter_converts_stable_dto_and_cancellation(tmp_path: Path) -> None:
    backend = EchoExecutor()
    adapter = PluginExecutorAdapter(_registration("echo", executor=backend))
    token = CancellationToken()

    result = adapter.execute(["tool", "check"], tmp_path, 12, token)

    assert result.command == ["tool", "check"]
    assert result.return_code == 0
    assert result.stdout == "done ✓"
    assert result.stdout_bytes == len("done ✓".encode())
    assert backend.request == PluginExecutionRequest(
        ("tool", "check"), tmp_path.resolve(), 12, token
    )


def test_executor_adapter_isolates_plugin_errors_and_invalid_responses(tmp_path: Path) -> None:
    class ExplodingExecutor:
        def execute(self, request: PluginExecutionRequest) -> PluginExecutionResponse:
            raise RuntimeError(f"failure in {request.working_directory / 'private.txt'}")

    adapter = PluginExecutorAdapter(_registration("broken-executor", executor=ExplodingExecutor()))
    with pytest.raises(PluginError, match=r"failure in <WORKSPACE>[/\\]private.txt"):
        adapter.execute(["tool"], tmp_path, 1)

    class InvalidExecutor:
        def execute(self, request: PluginExecutionRequest) -> Any:
            return {"return_code": 0}

    invalid = PluginExecutorAdapter(_registration("invalid-executor", executor=InvalidExecutor()))
    with pytest.raises(PluginError, match="invalid response type"):
        invalid.execute(["tool"], tmp_path, 1)

    with pytest.raises(PluginError, match="does not provide an executor"):
        PluginExecutorAdapter(_registration())


def test_execution_response_rejects_impossible_states() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        PluginExecutionResponse(None, "", "", -0.1)
    with pytest.raises(ValueError, match="timed out and cancelled"):
        PluginExecutionResponse(None, "", "", 0, timed_out=True, cancelled=True)
    with pytest.raises(ValueError, match="stdout_bytes"):
        PluginExecutionResponse(None, "", "", 0, stdout_bytes=-1)
    with pytest.raises(ValueError, match="return_code"):
        PluginExecutionResponse("zero", "", "", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tuple of text"):
        PluginExecutionResponse(None, "", "", 0, termination_diagnostics=(1,))  # type: ignore[arg-type]


def test_reporter_adapter_redacts_inputs_outputs_and_failures(tmp_path: Path) -> None:
    secret_path = tmp_path / "secret.txt"
    registration = _registration("summary")

    rendered = render_with_plugin(
        registration,
        _grade_result(),
        f"stdout {secret_path}",
        f"stderr {secret_path}",
        [tmp_path],
    )

    assert str(tmp_path) not in rendered
    assert "<WORKSPACE>" in rendered

    class ExplodingReporter:
        def render(self, request: PluginReportRequest) -> str:
            raise RuntimeError(f"failure at {secret_path}")

    broken = _registration("broken-reporter", reporter=ExplodingReporter())
    with pytest.raises(PluginError, match="failure at <WORKSPACE>"):
        render_with_plugin(broken, _grade_result(), "", "", [tmp_path])

    class InvalidReporter:
        def render(self, request: PluginReportRequest) -> Any:
            return 42

    invalid = _registration("invalid-reporter", reporter=InvalidReporter())
    with pytest.raises(PluginError, match="non-text"):
        render_with_plugin(invalid, _grade_result(), "", "")


def test_plugin_cli_lists_diagnostics_without_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PluginRegistry(
        {"example": _registration()},
        (
            PluginDiagnostic("example = package:plugin", "loaded", "reporter"),
            PluginDiagnostic("broken = bad:plugin", "failed", "load failed: [bold]boom[/bold]"),
        ),
    )
    monkeypatch.setattr(cli_module, "discover_plugins", lambda: registry)

    result = CliRunner().invoke(app, ["plugins"])

    assert result.exit_code == 0
    assert "1 plugin(s) loaded; 1 issue(s) isolated" in result.stdout
    assert "load failed: [bold]boom[/bold]" in result.stdout


def test_metadata_discovery_failure_does_not_break_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> Any:
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(plugin_module.importlib.metadata, "entry_points", unavailable)
    plugins = CliRunner().invoke(app, ["plugins"])
    version = CliRunner().invoke(app, ["version"])

    assert plugins.exit_code == 0
    assert "metadata unavailable" in plugins.stdout
    assert version.exit_code == 0
