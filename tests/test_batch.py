from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError
from rich.console import Console
from typer.testing import CliRunner

import repogym.batch as batch_module
import repogym.cli as cli_module
from repogym.batch import (
    BATCH_SCHEMA_VERSION,
    BatchJobResult,
    BatchResult,
    aggregate_exit_code,
    generate_batch_report,
    load_batch,
    load_batch_manifest,
    render_batch_junit,
    render_batch_sarif,
    run_batch,
)
from repogym.cli import app
from repogym.exceptions import BatchError, ValidationError
from repogym.exit_codes import ExitCode
from repogym.models import CacheEvidence, DimensionResult, GradeResult
from repogym.models import TestCounts as Counts

ROOT = Path(__file__).parents[1]


def _result(
    task_id: str,
    run_id: str,
    *,
    score: float = 100,
    status: str = "completed",
    violations: list[str] | None = None,
    cache_hit: bool | None = None,
) -> GradeResult:
    cache = None
    if cache_hit is not None:
        cache = CacheEvidence(key="a" * 64, hit=cache_hit)
    return GradeResult.model_validate(
        {
            "task_id": task_id,
            "task_fingerprint": "b" * 64,
            "run_id": run_id,
            "status": status,
            "score": score,
            "dimensions": {
                "correctness": DimensionResult(
                    score=min(score, 60), max_score=60, reason="batch fixture"
                ).model_dump()
            },
            "tests": Counts(
                passed=2 if score == 100 else 1,
                failed=0 if score == 100 else 1,
                total=2,
            ).model_dump(),
            "violations": violations or [],
            "duration_seconds": 0.25,
            "cache": cache.model_dump() if cache is not None else None,
        }
    )


def _write_manifest(path: Path, jobs: list[dict[str, str]], version: object = 1) -> Path:
    path.write_text(
        json.dumps({"schema_version": version, "jobs": jobs}),
        encoding="utf-8",
    )
    return path


def _write_batch(path: Path, batch: BatchResult) -> Path:
    path.mkdir()
    (path / "batch.json").write_text(
        json.dumps(batch.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _mixed_batch(secret_path: Path) -> BatchResult:
    low = _result(
        "low-task",
        "run-low",
        score=50,
        violations=["Forbidden path modified: src/private.py:7"],
    )
    good = _result("good-task", "run-good", cache_hit=True)
    return BatchResult(
        batch_id="batch-contract",
        exit_code=ExitCode.TASK_INVALID,
        jobs=[
            BatchJobResult(
                id="bad-job",
                status="task_invalid",
                exit_code=ExitCode.TASK_INVALID,
                error=f"invalid task at {secret_path}",
            ),
            BatchJobResult(
                id="good-job",
                status="success",
                exit_code=ExitCode.SUCCESS,
                task_id=good.task_id,
                run_id=good.run_id,
                score=good.score,
                cache_hit=True,
                result=good,
            ),
            BatchJobResult(
                id="low-job",
                status="score_not_passed",
                exit_code=ExitCode.SCORE_NOT_PASSED,
                task_id=low.task_id,
                run_id=low.run_id,
                score=low.score,
                result=low,
                error="Completed with score 50.00 below 100",
            ),
        ],
    )


def test_manifest_is_versioned_and_rejects_duplicates_and_blank_paths(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "batch.yaml",
        [{"id": "one", "task": "tasks/one", "submission": "submissions/one"}],
    )
    loaded = load_batch_manifest(manifest)
    assert loaded.schema_version == BATCH_SCHEMA_VERSION

    duplicate = _write_manifest(
        tmp_path / "duplicate.yaml",
        [
            {"id": "same", "task": "a", "submission": "a"},
            {"id": "same", "task": "b", "submission": "b"},
        ],
    )
    with pytest.raises(BatchError, match="duplicate batch job ids"):
        load_batch_manifest(duplicate)

    blank = _write_manifest(
        tmp_path / "blank.yaml",
        [{"id": "one", "task": " ", "submission": "submission"}],
    )
    with pytest.raises(BatchError, match="must not be blank"):
        load_batch_manifest(blank)

    for version in (True, "1", 2):
        invalid = _write_manifest(tmp_path / f"version-{version}.yaml", [], version)
        with pytest.raises(BatchError, match="schema version"):
            load_batch_manifest(invalid)


def test_batch_runs_in_job_id_order_and_continues_after_every_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = [
        {"id": "z-internal", "task": "internal", "submission": "candidate"},
        {"id": "a-success", "task": "success", "submission": "candidate"},
        {"id": "m-invalid", "task": "invalid", "submission": "candidate"},
        {"id": "e-environment", "task": "environment", "submission": "candidate"},
        {"id": "s-score", "task": "score", "submission": "candidate"},
        {"id": "x-execution", "task": "execution", "submission": "candidate"},
    ]
    manifest = _write_manifest(tmp_path / "batch.yaml", jobs)
    calls: list[str] = []
    results = {
        "success": _result("success-task", "run-success"),
        "score": _result("score-task", "run-score", score=80),
        "execution": _result("execution-task", "run-execution", score=0, status="timed_out"),
    }

    def fake_grade(task: Path, submission: Path, **_kwargs: object) -> Path:
        calls.append(task.name)
        assert submission == (tmp_path / "candidate").resolve()
        if task.name == "invalid":
            raise ValidationError(f"invalid {task}")
        if task.name == "environment":
            raise OSError(f"unavailable {task}")
        if task.name == "internal":
            raise RuntimeError(f"unexpected {task}")
        return tmp_path / f"run-{task.name}"

    def fake_load(run: Path) -> tuple[GradeResult, str, str]:
        return results[run.name.removeprefix("run-")], "", ""

    monkeypatch.setattr(batch_module, "grade_submission", fake_grade)
    monkeypatch.setattr(batch_module, "load_run", fake_load)

    batch_dir = run_batch(
        manifest,
        output_root=tmp_path / "batches",
        runs_root=tmp_path / "runs",
        cache_root=tmp_path / "cache",
    )
    batch = load_batch(batch_dir)

    assert calls == ["success", "environment", "invalid", "score", "execution", "internal"]
    assert [job.id for job in batch.jobs] == sorted(job["id"] for job in jobs)
    assert [job.status for job in batch.jobs] == [
        "success",
        "environment_error",
        "task_invalid",
        "score_not_passed",
        "execution_failed",
        "internal_error",
    ]
    assert batch.exit_code == ExitCode.INTERNAL_ERROR
    serialized = (batch_dir / "batch.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in serialized


def test_duplicate_task_jobs_reuse_cache_and_score_100(tmp_path: Path) -> None:
    task = ROOT / "tasks" / "python-cache-ttl"
    submission = ROOT / "examples" / "submissions" / "cache-ttl-fixed"
    manifest = _write_manifest(
        tmp_path / "batch.yaml",
        [
            {"id": "second-copy", "task": str(task), "submission": str(submission)},
            {"id": "first-copy", "task": str(task), "submission": str(submission)},
        ],
    )

    batch_dir = run_batch(
        manifest,
        output_root=tmp_path / "batches",
        runs_root=tmp_path / "runs",
        cache_root=tmp_path / "cache",
    )
    batch = load_batch(batch_dir)

    assert batch.exit_code == ExitCode.SUCCESS
    assert [job.id for job in batch.jobs] == ["first-copy", "second-copy"]
    assert [job.score for job in batch.jobs] == [100, 100]
    assert [job.cache_hit for job in batch.jobs] == [False, True]
    assert batch.jobs[0].run_id != batch.jobs[1].run_id


def test_aggregate_exit_code_uses_documented_severity_not_numeric_order() -> None:
    assert aggregate_exit_code([]) == ExitCode.SUCCESS
    assert (
        aggregate_exit_code([ExitCode.SCORE_NOT_PASSED, ExitCode.TASK_INVALID])
        == ExitCode.TASK_INVALID
    )
    assert (
        aggregate_exit_code([ExitCode.EXECUTION_FAILED, ExitCode.ENVIRONMENT_ERROR])
        == ExitCode.ENVIRONMENT_ERROR
    )


def test_batch_result_rejects_unsorted_jobs_and_incorrect_aggregate() -> None:
    first = BatchJobResult(id="a", status="success", exit_code=ExitCode.SUCCESS)
    second = BatchJobResult(id="b", status="task_invalid", exit_code=ExitCode.TASK_INVALID)
    with pytest.raises(PydanticValidationError, match="sorted"):
        BatchResult(batch_id="bad", exit_code=ExitCode.TASK_INVALID, jobs=[second, first])
    with pytest.raises(PydanticValidationError, match="does not match"):
        BatchResult(batch_id="bad", exit_code=ExitCode.SUCCESS, jobs=[first, second])


def test_batch_reports_are_deterministic_structured_and_redacted(tmp_path: Path) -> None:
    batch_dir = _write_batch(
        tmp_path / "batch-run", _mixed_batch(tmp_path / "batch-run" / "secret")
    )

    first_json = generate_batch_report(batch_dir, "json")
    second_json = generate_batch_report(batch_dir, "json")
    junit = render_batch_junit(load_batch(batch_dir))
    sarif = render_batch_sarif(load_batch(batch_dir))
    console = Console(record=True, width=160)
    assert generate_batch_report(batch_dir, "terminal", console=console) is None

    assert first_json == second_json
    assert first_json is not None and str(tmp_path) not in first_json
    assert [job["id"] for job in json.loads(first_json)["jobs"]] == [
        "bad-job",
        "good-job",
        "low-job",
    ]
    suites = ET.fromstring(junit)
    assert suites.attrib["tests"] == "3"
    assert suites.attrib["failures"] == "1"
    assert suites.attrib["errors"] == "1"
    low_properties = suites.findall("testsuite")[2].find("properties")
    assert low_properties is not None
    assert {item.attrib["name"] for item in low_properties} >= {
        "repogym.score",
        "repogym.tests.total",
    }
    sarif_document = json.loads(sarif)
    sarif_results = sarif_document["runs"][0]["results"]
    assert [(item["properties"]["batchJobId"], item["ruleId"]) for item in sarif_results] == [
        ("bad-job", "repogym/batch-outcome"),
        ("low-job", "repogym/batch-outcome"),
        ("low-job", "repogym/forbidden-path"),
    ]
    assert str(tmp_path) not in junit + sarif + console.export_text()


@pytest.mark.parametrize(
    ("format_name", "marker"),
    [("json", '"batch_id"'), ("junit", "<testsuites"), ("sarif", '"2.1.0"')],
)
def test_batch_report_cli_replays_without_execution_and_preserves_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    format_name: str,
    marker: str,
) -> None:
    batch_dir = _write_batch(tmp_path / "batch-run", _mixed_batch(tmp_path / "batch-run"))

    def must_not_execute(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("report replay executed a task")

    monkeypatch.setattr(batch_module, "grade_submission", must_not_execute)
    result = CliRunner().invoke(
        app,
        ["batch", "report", str(batch_dir), "--format", format_name],
    )

    assert result.exit_code == ExitCode.TASK_INVALID
    assert marker in result.stdout


def test_batch_run_cli_writes_requested_report_before_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch_dir = _write_batch(tmp_path / "batch-run", _mixed_batch(tmp_path / "batch-run"))
    monkeypatch.setattr(cli_module, "run_batch", lambda *_args, **_kwargs: batch_dir)
    output = tmp_path / "batch.xml"

    result = CliRunner().invoke(
        app,
        [
            "batch",
            "run",
            "manifest.yaml",
            "--format",
            "junit",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == ExitCode.TASK_INVALID
    assert ET.parse(output).getroot().tag == "testsuites"
    assert "Batch artifacts" in result.stdout


def test_batch_run_cli_keeps_machine_stdout_parseable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch_dir = _write_batch(tmp_path / "batch-run", _mixed_batch(tmp_path / "batch-run"))
    monkeypatch.setattr(cli_module, "run_batch", lambda *_args, **_kwargs: batch_dir)

    result = CliRunner().invoke(
        app,
        ["batch", "run", "manifest.yaml", "--format", "json"],
    )

    assert result.exit_code == ExitCode.TASK_INVALID
    assert json.loads(result.stdout)["batch_id"] == "batch-contract"
    assert "Batch artifacts" not in result.stdout


def test_batch_cli_rejects_invalid_manifest_with_stable_code(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "batch.yaml", [], version=99)

    result = CliRunner().invoke(app, ["batch", "run", str(manifest)])

    assert result.exit_code == ExitCode.TASK_INVALID
    assert "Unsupported batch schema version" in result.stderr
