"""Versioned, structured evidence for persisted grading runs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from repogym.exceptions import ReportError
from repogym.models import GradeResult

EVIDENCE_SCHEMA_VERSION = 2
EvidenceValue = str | int | float | bool | None


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["artifact", "command", "environment", "test"]
    source: str
    observed_at: datetime
    status: Literal["failed", "info", "passed", "warning"]
    summary: str
    task_id: str
    details: dict[str, EvidenceValue]


class EvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    task_id: str
    task_fingerprint: str | None = None
    records: list[EvidenceRecord]

    @model_validator(mode="before")
    @classmethod
    def migrate_schema_one(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("schema_version") == 1:
            migrated = dict(value)
            migrated["schema_version"] = EVIDENCE_SCHEMA_VERSION
            return migrated
        return value


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_evidence(
    result: GradeResult,
    observed_at: datetime,
    stdout: str,
    stderr: str,
) -> EvidenceDocument:
    """Build a deterministically ordered evidence document from sanitized values."""
    records: list[EvidenceRecord] = []
    execution = result.execution
    if execution is not None:
        command_status: Literal["failed", "passed", "warning"] = (
            "warning"
            if execution.cancelled or execution.timed_out
            else "passed"
            if execution.exit_code == 0
            else "failed"
        )
        records.append(
            EvidenceRecord(
                kind="command",
                source="executor",
                observed_at=observed_at,
                status=command_status,
                summary="Task test command execution",
                task_id=result.task_id,
                details={
                    "argv": json.dumps(execution.argv, ensure_ascii=False),
                    "cancelled": execution.cancelled,
                    "duration_seconds": execution.duration_seconds,
                    "exit_code": execution.exit_code,
                    "timed_out": execution.timed_out,
                },
            )
        )
    records.extend(
        [
            EvidenceRecord(
                kind="test",
                source="pytest_summary",
                observed_at=observed_at,
                status="passed" if result.tests.failed == 0 else "failed",
                summary="Parsed test statistics",
                task_id=result.task_id,
                details={
                    "failed": result.tests.failed,
                    "passed": result.tests.passed,
                    "total": result.tests.total,
                },
            ),
        ]
    )
    environment = result.environment
    if environment.availability == "available" and environment.snapshot is not None:
        snapshot = environment.snapshot
        records.append(
            EvidenceRecord(
                kind="environment",
                source="runtime_environment",
                observed_at=observed_at,
                status="info",
                summary="Versioned non-secret runtime environment",
                task_id=result.task_id,
                details={
                    "architecture": snapshot.architecture,
                    "dependencies": json.dumps(snapshot.dependencies, sort_keys=True),
                    "executor": snapshot.executor,
                    "fingerprint": environment.fingerprint,
                    "operating_system": snapshot.operating_system,
                    "operating_system_release": snapshot.operating_system_release,
                    "python_implementation": snapshot.python_implementation,
                    "python_version": snapshot.python_version,
                    "repogym_version": snapshot.repogym_version,
                    "schema_version": environment.schema_version,
                },
            )
        )
    else:
        records.append(
            EvidenceRecord(
                kind="environment",
                source="runtime_environment",
                observed_at=observed_at,
                status="warning",
                summary="Runtime environment unavailable",
                task_id=result.task_id,
                details={"availability": "unavailable", "reason": environment.reason},
            )
        )
    test_evidence = result.test_evidence
    if test_evidence.availability == "available":
        status_map: dict[
            Literal["passed", "failed", "error", "skipped"],
            Literal["failed", "info", "passed", "warning"],
        ] = {
            "passed": "passed",
            "failed": "failed",
            "error": "failed",
            "skipped": "warning",
        }
        for case in test_evidence.cases:
            records.append(
                EvidenceRecord(
                    kind="test",
                    source=f"pytest_junit:{case.id}",
                    observed_at=observed_at,
                    status=status_map[case.status],
                    summary=f"Test case {case.id}",
                    task_id=result.task_id,
                    details={
                        "case_id": case.id,
                        "duration_seconds": case.duration_seconds,
                        "failure_summary": case.failure_summary,
                        "output_refs": json.dumps(case.output_refs),
                        "status": case.status,
                    },
                )
            )
    else:
        records.append(
            EvidenceRecord(
                kind="test",
                source="pytest_junit",
                observed_at=observed_at,
                status="warning",
                summary="Per-test results unavailable",
                task_id=result.task_id,
                details={
                    "availability": test_evidence.availability,
                    "reason": test_evidence.reason,
                },
            )
        )
    for name, content in (("stderr.txt", stderr), ("stdout.txt", stdout)):
        records.append(
            EvidenceRecord(
                kind="artifact",
                source=name,
                observed_at=observed_at,
                status="info",
                summary="Sanitized process output artifact",
                task_id=result.task_id,
                details={"bytes": len(content.encode("utf-8")), "sha256": _digest(content)},
            )
        )
    records.sort(key=lambda item: (item.kind, item.source, item.summary))
    return EvidenceDocument(
        task_id=result.task_id,
        task_fingerprint=result.task_fingerprint,
        records=records,
    )


def load_evidence(run_directory: Path) -> EvidenceDocument:
    """Load evidence, synthesizing schema v1 for runs created before evidence.json."""
    try:
        result_raw: Any = json.loads((run_directory / "result.json").read_text(encoding="utf-8"))
        result = GradeResult.model_validate(result_raw)
        metadata: Any = json.loads((run_directory / "metadata.json").read_text(encoding="utf-8"))
        evidence_path = run_directory / "evidence.json"
        if evidence_path.is_file():
            raw: Any = json.loads(evidence_path.read_text(encoding="utf-8"))
            document = EvidenceDocument.model_validate(raw)
            has_per_test = any(
                record.source.startswith("pytest_junit") for record in document.records
            )
            if not has_per_test:
                document.records.append(
                    EvidenceRecord(
                        kind="test",
                        source="pytest_junit",
                        observed_at=datetime.fromisoformat(str(metadata["created_at"])),
                        status="warning",
                        summary="Per-test results unavailable",
                        task_id=result.task_id,
                        details={"availability": "unavailable", "reason": "legacy_run"},
                    )
                )
                document.records.sort(key=lambda item: (item.kind, item.source, item.summary))
            return document
        observed_at = datetime.fromisoformat(str(metadata["created_at"]))
        stdout = (run_directory / "stdout.txt").read_text(encoding="utf-8")
        stderr = (run_directory / "stderr.txt").read_text(encoding="utf-8")
        return build_evidence(result, observed_at, stdout, stderr)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ReportError(f"Invalid execution evidence in {run_directory}: {exc}") from exc
