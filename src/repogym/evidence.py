"""Versioned, structured evidence for persisted grading runs."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from repogym.exceptions import ReportError
from repogym.models import GradeResult

EVIDENCE_SCHEMA_VERSION = 1
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

    schema_version: Literal[1] = 1
    task_id: str
    task_fingerprint: str | None = None
    records: list[EvidenceRecord]


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
            EvidenceRecord(
                kind="environment",
                source="python_runtime",
                observed_at=observed_at,
                status="info",
                summary="Non-secret runtime identity",
                task_id=result.task_id,
                details={
                    "implementation": platform.python_implementation(),
                    "platform": platform.system().lower(),
                    "python_version": platform.python_version(),
                },
            ),
        ]
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
            return EvidenceDocument.model_validate(raw)
        observed_at = datetime.fromisoformat(str(metadata["created_at"]))
        stdout = (run_directory / "stdout.txt").read_text(encoding="utf-8")
        stderr = (run_directory / "stderr.txt").read_text(encoding="utf-8")
        return build_evidence(result, observed_at, stdout, stderr)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ReportError(f"Invalid execution evidence in {run_directory}: {exc}") from exc
