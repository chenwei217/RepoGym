"""Deterministic batch grading, persistence, and report replay."""

from __future__ import annotations

import json
import os
import uuid

# This module creates XML and never parses untrusted XML.
import xml.etree.ElementTree as ET  # nosec B405
from collections.abc import Iterable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from repogym.exceptions import (
    BatchError,
    CacheError,
    ExecutionError,
    RepoGymError,
    ReportError,
)
from repogym.executors import CancellationToken
from repogym.exit_codes import ExitCode
from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.models import GradeResult, StrictModel
from repogym.reports import load_run, render_sarif
from repogym.reproducibility import task_fingerprint
from repogym.scheduling import MAX_WORKERS, run_groups
from repogym.security import redact_sensitive_text, redact_value

BATCH_SCHEMA_VERSION = 1
BatchFormat = Literal["terminal", "json", "junit", "sarif"]
BatchJobStatus = Literal[
    "success",
    "score_not_passed",
    "execution_failed",
    "task_invalid",
    "environment_error",
    "internal_error",
]

_EXIT_PRIORITY = {
    ExitCode.SUCCESS: 0,
    ExitCode.SCORE_NOT_PASSED: 1,
    ExitCode.EXECUTION_FAILED: 2,
    ExitCode.TASK_INVALID: 3,
    ExitCode.ENVIRONMENT_ERROR: 4,
    ExitCode.INTERNAL_ERROR: 5,
}


class BatchJobSpec(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    task: str = Field(min_length=1)
    submission: str = Field(min_length=1)
    task_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("task", "submission")
    @classmethod
    def path_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class BatchManifest(StrictModel):
    schema_version: Literal[1]
    jobs: list[BatchJobSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_job_ids(self) -> BatchManifest:
        ids = [job.id for job in self.jobs]
        duplicates = sorted({job_id for job_id in ids if ids.count(job_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate batch job ids: {', '.join(duplicates)}")
        return self


class BatchJobResult(StrictModel):
    id: str
    status: BatchJobStatus
    exit_code: ExitCode
    task_id: str | None = None
    run_id: str | None = None
    score: float | None = None
    cache_hit: bool | None = None
    result: GradeResult | None = None
    error: str | None = None


class BatchResult(StrictModel):
    schema_version: Literal[1] = 1
    batch_id: str
    exit_code: ExitCode
    jobs: list[BatchJobResult] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_and_sorted_jobs(self) -> BatchResult:
        ids = [job.id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("batch result contains duplicate job ids")
        if ids != sorted(ids):
            raise ValueError("batch result jobs must be sorted by id")
        expected = aggregate_exit_code(job.exit_code for job in self.jobs)
        if self.exit_code != expected:
            raise ValueError("batch exit code does not match job outcomes")
        return self


def aggregate_exit_code(codes: Iterable[ExitCode]) -> ExitCode:
    """Return the most severe stable outcome in an order independent of job input."""
    return max(codes, key=lambda code: _EXIT_PRIORITY[code], default=ExitCode.SUCCESS)


def _validation_message(exc: PydanticValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        messages.append(f"{location}: {error['msg']}")
    return "Invalid batch manifest:\n  - " + "\n  - ".join(messages)


def load_batch_manifest(path: Path) -> BatchManifest:
    """Load a strict version-1 YAML manifest without resolving job paths yet."""
    if not path.is_file():
        raise BatchError(f"Batch manifest does not exist: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise BatchError(f"Could not read batch manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise BatchError("Batch manifest must contain a YAML mapping")
    version = raw.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise BatchError("Invalid batch schema version: expected integer 1")
    if version != BATCH_SCHEMA_VERSION:
        raise BatchError(f"Unsupported batch schema version: {version}; supported version: 1")
    try:
        return BatchManifest.model_validate(raw)
    except PydanticValidationError as exc:
        raise BatchError(_validation_message(exc)) from exc


def _resolve_job_path(base: Path, configured: str) -> Path:
    path = Path(configured)
    try:
        return path.resolve() if path.is_absolute() else (base / path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ReportError("Cannot resolve batch input path") from exc


def _new_batch_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _job_from_result(job_id: str, result: GradeResult) -> BatchJobResult:
    if result.status != "completed":
        status: BatchJobStatus = "execution_failed"
        code = ExitCode.EXECUTION_FAILED
        error = f"Execution status: {result.status}"
    elif result.score < 100:
        status = "score_not_passed"
        code = ExitCode.SCORE_NOT_PASSED
        error = f"Completed with score {result.score:.2f} below 100"
    else:
        status = "success"
        code = ExitCode.SUCCESS
        error = None
    return BatchJobResult(
        id=job_id,
        status=status,
        exit_code=code,
        task_id=result.task_id,
        run_id=result.run_id,
        score=result.score,
        cache_hit=result.cache.hit if result.cache is not None else None,
        result=result,
        error=error,
    )


def _failed_job(
    job_id: str,
    status: BatchJobStatus,
    code: ExitCode,
    exc: Exception,
    sensitive_roots: Iterable[Path],
) -> BatchJobResult:
    return BatchJobResult(
        id=job_id,
        status=status,
        exit_code=code,
        error=redact_sensitive_text(str(exc), sensitive_roots),
    )


def _run_job(
    job: BatchJobSpec,
    base: Path,
    runs_root: Path,
    cache_root: Path | None,
    token: CancellationToken,
) -> BatchJobResult:
    roots: tuple[Path, ...] = (Path.cwd().resolve(), base)
    if token.cancelled:
        return _failed_job(
            job.id,
            "execution_failed",
            ExitCode.EXECUTION_FAILED,
            ExecutionError("Batch cancelled before job started"),
            roots,
        )
    try:
        task = _resolve_job_path(base, job.task)
        submission = _resolve_job_path(base, job.submission)
        roots = (Path.cwd().resolve(), base, task, submission)
        if job.task_fingerprint is not None:
            actual = task_fingerprint(task, load_task(task))
            if actual != job.task_fingerprint:
                raise BatchError("Pinned task fingerprint mismatch; execution refused")
        run_directory = grade_submission(
            task, submission, output_root=runs_root, cache_root=cache_root, cancellation_token=token
        )
        result, _, _ = load_run(run_directory)
    except ExecutionError as exc:
        return _failed_job(job.id, "execution_failed", ExitCode.EXECUTION_FAILED, exc, roots)
    except (CacheError, ReportError, OSError) as exc:
        return _failed_job(job.id, "environment_error", ExitCode.ENVIRONMENT_ERROR, exc, roots)
    except RepoGymError as exc:
        return _failed_job(job.id, "task_invalid", ExitCode.TASK_INVALID, exc, roots)
    except Exception as exc:
        return _failed_job(job.id, "internal_error", ExitCode.INTERNAL_ERROR, exc, roots)
    return _job_from_result(job.id, result)


def run_batch(
    manifest_path: Path,
    output_root: Path = Path(".repogym/batches"),
    runs_root: Path = Path(".repogym/runs"),
    cache_root: Path | None = Path(".repogym/cache"),
    *,
    max_workers: int = 1,
    cancellation_token: CancellationToken | None = None,
) -> Path:
    """Grade bounded independent groups and persist results in lexical job order."""
    if type(max_workers) is not int or not 1 <= max_workers <= MAX_WORKERS:
        raise BatchError(f"workers must be an integer between 1 and {MAX_WORKERS}")
    manifest_file = manifest_path.resolve()
    manifest = load_batch_manifest(manifest_file)
    base = manifest_file.parent
    ordered = sorted(manifest.jobs, key=lambda item: item.id)
    token = cancellation_token or CancellationToken()
    groups: list[list[BatchJobSpec]]
    if max_workers == 1:
        groups = [[job] for job in ordered]
    else:
        by_pair: dict[tuple[Path, Path], list[BatchJobSpec]] = {}
        for job in ordered:
            try:
                key = (_resolve_job_path(base, job.task), _resolve_job_path(base, job.submission))
            except ReportError:
                key = (base / job.id, base / job.id)
            by_pair.setdefault(key, []).append(job)
        groups = list(by_pair.values())

    def grade_job(job: BatchJobSpec) -> BatchJobResult:
        return _run_job(job, base, runs_root, cache_root, token)

    jobs = sorted(
        run_groups(groups, grade_job, max_workers=max_workers, cancellation_token=token),
        key=lambda item: item.id,
    )

    batch_id = _new_batch_id()
    batch = BatchResult(
        batch_id=batch_id,
        exit_code=aggregate_exit_code(job.exit_code for job in jobs),
        jobs=jobs,
    )
    batch_directory = output_root.resolve() / batch_id
    batch_directory.mkdir(parents=True, exist_ok=False)
    _atomic_write_json(
        batch_directory / "schedule.json",
        {
            "schema_version": 1,
            "max_workers": max_workers,
            "group_count": len(groups),
            "same_pair_policy": "serial",
            "result_order": "job_id",
            "cancellation_requested": token.cancelled,
        },
    )
    _atomic_write_json(batch_directory / "batch.json", batch.model_dump(mode="json"))
    return batch_directory


def load_batch(batch_path: Path) -> BatchResult:
    """Load and validate a persisted batch result, applying report redaction again."""
    source = batch_path / "batch.json" if batch_path.is_dir() else batch_path
    try:
        raw: Any = json.loads(source.read_text(encoding="utf-8"))
        sanitized = redact_value(raw, [source.parent.resolve()])
        return BatchResult.model_validate(sanitized)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReportError(f"Invalid batch result {batch_path}: {exc}") from exc


def render_batch_terminal(batch: BatchResult, console: Console) -> None:
    """Render a stable job-level summary."""
    table = Table("Job", "Task", "Status", "Score", "Tests", "Cache", "Run")
    for job in batch.jobs:
        result = job.result
        tests = f"{result.tests.passed}/{result.tests.total}" if result is not None else "-"
        cache = "hit" if job.cache_hit else "miss" if job.cache_hit is False else "-"
        table.add_row(
            job.id,
            job.task_id or "-",
            job.status,
            f"{job.score:.2f}" if job.score is not None else "-",
            tests,
            cache,
            job.run_id or "-",
        )
    console.print(table)
    for job in batch.jobs:
        if job.error:
            console.print(f"[red]{escape(job.id)}:[/red] {escape(job.error)}")
    console.print(
        f"Batch {batch.batch_id}: {len(batch.jobs)} job(s); exit code {int(batch.exit_code)}"
    )


def render_batch_junit(batch: BatchResult) -> str:
    """Render one deterministic JUnit testcase per batch job."""
    failures = sum(job.status in {"score_not_passed", "execution_failed"} for job in batch.jobs)
    errors = sum(
        job.status in {"task_invalid", "environment_error", "internal_error"} for job in batch.jobs
    )
    total_time = sum(job.result.duration_seconds for job in batch.jobs if job.result is not None)
    suites = ET.Element(
        "testsuites",
        {
            "name": "RepoGym batch",
            "tests": str(len(batch.jobs)),
            "failures": str(failures),
            "errors": str(errors),
            "skipped": "0",
            "time": f"{total_time:.3f}",
        },
    )
    for job in batch.jobs:
        result = job.result
        duration = result.duration_seconds if result is not None else 0.0
        failed = job.status in {"score_not_passed", "execution_failed"}
        errored = job.status in {"task_invalid", "environment_error", "internal_error"}
        suite = ET.SubElement(
            suites,
            "testsuite",
            {
                "name": job.id,
                "tests": "1",
                "failures": "1" if failed else "0",
                "errors": "1" if errored else "0",
                "skipped": "0",
                "time": f"{duration:.3f}",
            },
        )
        properties = ET.SubElement(suite, "properties")
        if result is not None:
            for name, value in (
                ("repogym.score", f"{result.score:.2f}"),
                ("repogym.tests.passed", str(result.tests.passed)),
                ("repogym.tests.failed", str(result.tests.failed)),
                ("repogym.tests.total", str(result.tests.total)),
            ):
                ET.SubElement(properties, "property", {"name": name, "value": value})
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": job.task_id or "repogym.batch",
                "name": job.id,
                "time": f"{duration:.3f}",
            },
        )
        message = redact_sensitive_text(job.error or job.status)
        if failed:
            child = ET.SubElement(case, "failure", {"message": message})
            child.text = message
        elif errored:
            child = ET.SubElement(case, "error", {"message": message})
            child.text = message
    ET.indent(suites, space="  ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ET.tostring(suites, encoding="unicode", short_empty_elements=True)
        + "\n"
    )


def render_batch_sarif(batch: BatchResult) -> str:
    """Render violations and job-level failures as one deterministic SARIF run."""
    results: list[dict[str, Any]] = []
    for job in batch.jobs:
        if job.result is not None:
            run = json.loads(render_sarif(job.result))["runs"][0]
            for item in run["results"]:
                item["properties"] = {"batchJobId": job.id}
                results.append(item)
        if job.status != "success":
            message = redact_sensitive_text(job.error or job.status)
            results.append(
                {
                    "ruleId": "repogym/batch-outcome",
                    "level": "error",
                    "message": {"text": message},
                    "properties": {"batchJobId": job.id, "exitCode": int(job.exit_code)},
                }
            )
    results.sort(
        key=lambda item: (
            str(item.get("properties", {}).get("batchJobId", "")),
            str(item["ruleId"]),
            str(item["message"]["text"]),
        )
    )
    log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "automationDetails": {"id": batch.batch_id},
                "tool": {
                    "driver": {
                        "name": "RepoGym",
                        "informationUri": "https://github.com/chenwei217/RepoGym",
                        "rules": [
                            {"id": "repogym/batch-outcome", "name": "BatchOutcome"},
                            {"id": "repogym/forbidden-path", "name": "ForbiddenPath"},
                            {"id": "repogym/scope", "name": "ScopeControl"},
                        ],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def generate_batch_report(
    batch_path: Path,
    format_name: BatchFormat = "terminal",
    output: Path | None = None,
    console: Console | None = None,
) -> str | None:
    """Replay a persisted batch into any supported summary format."""
    batch = load_batch(batch_path)
    if format_name == "terminal":
        if output is None:
            render_batch_terminal(batch, console or Console())
            return None
        buffer = StringIO()
        recording = Console(file=buffer, width=140, color_system=None)
        render_batch_terminal(batch, recording)
        rendered = buffer.getvalue()
    elif format_name == "json":
        rendered = (
            json.dumps(batch.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
    elif format_name == "junit":
        rendered = render_batch_junit(batch)
    else:
        rendered = render_batch_sarif(batch)
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    return rendered
