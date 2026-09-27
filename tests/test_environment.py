from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

import repogym.environment as environment_module
from repogym.cli import app
from repogym.environment import collect_runtime_environment, environment_fingerprint
from repogym.evidence import load_evidence
from repogym.grader import grade_submission
from repogym.models import (
    DimensionResult,
    GradeResult,
    RuntimeEnvironmentEvidence,
    RuntimeEnvironmentSnapshot,
)
from repogym.models import (
    TestCounts as Counts,
)
from repogym.reports import generate_report, load_run, render_terminal

ROOT = Path(__file__).parents[1]


def _snapshot(
    *,
    python_version: str = "3.11.9",
    rich_version: str = "13.9.0",
) -> RuntimeEnvironmentSnapshot:
    return RuntimeEnvironmentSnapshot(
        python_implementation="CPython",
        python_version=python_version,
        operating_system="windows",
        operating_system_release="2025",
        architecture="amd64",
        dependencies={"pydantic": "2.11.0", "rich": rich_version},
        repogym_version="0.1.0",
        executor="local:stdout=1048576:stderr=1048576",
    )


def _environment(snapshot: RuntimeEnvironmentSnapshot) -> RuntimeEnvironmentEvidence:
    return RuntimeEnvironmentEvidence(
        availability="available",
        fingerprint=environment_fingerprint(snapshot),
        snapshot=snapshot,
        reason="collected",
    )


def _result(environment: RuntimeEnvironmentEvidence) -> GradeResult:
    return GradeResult(
        task_id="sample-task",
        run_id="run-1",
        status="completed",
        score=100,
        dimensions={"correctness": DimensionResult(score=60, max_score=60, reason="passed")},
        tests=Counts(passed=1, total=1),
        violations=[],
        duration_seconds=0.1,
        environment=environment,
    )


def _freeze_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment_module.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(environment_module.platform, "python_version", lambda: "3.11.9")
    monkeypatch.setattr(environment_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(environment_module.platform, "release", lambda: "2025")
    monkeypatch.setattr(environment_module.platform, "machine", lambda: "AMD64")
    versions = {
        name: f"{index}.0.0"
        for index, name in enumerate(environment_module.DEPENDENCY_DISTRIBUTIONS, 1)
    }
    monkeypatch.setattr(environment_module.metadata, "version", versions.__getitem__)


def test_environment_snapshot_and_fingerprint_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_environment(monkeypatch)

    first = collect_runtime_environment()
    second = collect_runtime_environment()

    assert first == second
    assert first.snapshot is not None
    assert list(first.snapshot.dependencies) == sorted(first.snapshot.dependencies)
    assert first.fingerprint == first.snapshot.fingerprint()


def test_environment_snapshot_excludes_local_identity_and_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _freeze_environment(monkeypatch)
    monkeypatch.setenv("REPOGYM_TEST_TOKEN", "do-not-record-this-value")
    monkeypatch.setenv("HOME", str(tmp_path / "private-home"))
    monkeypatch.setattr(
        environment_module.platform,
        "node",
        lambda: (_ for _ in ()).throw(AssertionError("hostname must not be read")),
    )

    encoded = collect_runtime_environment().model_dump_json()

    assert "do-not-record-this-value" not in encoded
    assert str(tmp_path) not in encoded
    assert "private-home" not in encoded


def test_missing_dependency_is_explicit_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_environment(monkeypatch)
    original = environment_module.metadata.version

    def version(name: str) -> str:
        if name == "Jinja2":
            raise metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(environment_module.metadata, "version", version)

    result = collect_runtime_environment()

    assert result.snapshot is not None
    assert result.snapshot.dependencies["jinja2"] == "unavailable"


def test_environment_fingerprint_rejects_mutated_snapshot() -> None:
    raw = _environment(_snapshot()).model_dump(mode="json")
    raw["snapshot"]["python_version"] = "3.12.0"

    with pytest.raises(ValueError, match="fingerprint"):
        RuntimeEnvironmentEvidence.model_validate(raw)


def test_environment_cli_terminal_and_json_share_the_same_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _environment(_snapshot())
    monkeypatch.setattr("repogym.cli.collect_runtime_environment", lambda: expected)
    runner = CliRunner()

    terminal = runner.invoke(app, ["environment"])
    structured = runner.invoke(app, ["environment", "--format", "json"])

    assert terminal.exit_code == 0
    assert "CPython 3.11.9" in terminal.stdout
    assert expected.fingerprint in terminal.stdout
    assert structured.exit_code == 0
    assert json.loads(structured.stdout) == expected.model_dump(mode="json")


def test_reports_render_environment_and_legacy_availability(tmp_path: Path) -> None:
    result = _result(_environment(_snapshot()))
    console = Console(record=True, width=140)
    render_terminal(result, console)
    assert result.environment.fingerprint is not None
    assert result.environment.fingerprint[:12] in console.export_text()

    run = tmp_path / "run"
    run.mkdir()
    (run / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    (run / "stdout.txt").write_text("", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    html = generate_report(run, "html")
    assert html is not None
    assert result.environment.fingerprint in html
    assert "CPython 3.11.9" in html

    raw = result.model_dump(mode="json")
    raw.pop("environment")
    (run / "result.json").write_text(json.dumps(raw), encoding="utf-8")
    legacy, _, _ = load_run(run)
    assert legacy.environment.reason == "legacy_run"


def test_grading_persists_environment_in_result_metadata_and_evidence(
    tmp_path: Path,
) -> None:
    run = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )

    result, _, _ = load_run(run)
    metadata_raw = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    evidence = load_evidence(run)

    assert result.environment.availability == "available"
    assert metadata_raw["environment"] == result.environment.model_dump(mode="json")
    runtime = [item for item in evidence.records if item.source == "runtime_environment"]
    assert len(runtime) == 1
    assert runtime[0].details["fingerprint"] == result.environment.fingerprint
