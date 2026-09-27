from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repogym.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceDocument,
    build_evidence,
    load_evidence,
)
from repogym.exceptions import ReportError
from repogym.grader import grade_submission
from repogym.models import DimensionResult, ExecutionEvidence, GradeResult
from repogym.models import TestCounts as Counts

ROOT = Path(__file__).parents[1]


def sample_result() -> GradeResult:
    dimension = DimensionResult(score=25, max_score=25, reason="passed")
    return GradeResult(
        task_id="sample-task",
        task_fingerprint="a" * 64,
        run_id="run-1",
        status="completed",
        score=100,
        dimensions={"correctness": dimension},
        tests=Counts(passed=2, failed=0, total=2),
        violations=[],
        duration_seconds=0.2,
        execution=ExecutionEvidence(
            argv=["<ABSOLUTE_PATH>", "-m", "pytest"],
            exit_code=0,
            timed_out=False,
            test_statistics_source="pytest_summary",
        ),
    )


def test_evidence_round_trip_is_versioned_and_deterministically_sorted() -> None:
    document = build_evidence(sample_result(), datetime(2026, 1, 2, tzinfo=UTC), "2 passed\n", "")
    serialized = document.model_dump(mode="json")
    assert serialized["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert EvidenceDocument.model_validate(serialized) == document
    keys = [(item.kind, item.source, item.summary) for item in document.records]
    assert keys == sorted(keys)
    assert {item.kind for item in document.records} == {
        "artifact",
        "command",
        "environment",
        "test",
    }


def test_evidence_rejects_unknown_schema_and_fields() -> None:
    raw = build_evidence(sample_result(), datetime.now(UTC), "", "").model_dump(mode="json")
    raw["schema_version"] = 3
    with pytest.raises(ValueError):
        EvidenceDocument.model_validate(raw)
    raw["schema_version"] = 1
    raw["unexpected"] = True
    with pytest.raises(ValueError):
        EvidenceDocument.model_validate(raw)


def test_evidence_migrates_schema_one_in_memory() -> None:
    raw = build_evidence(sample_result(), datetime.now(UTC), "", "").model_dump(mode="json")
    raw["schema_version"] = 1

    migrated = EvidenceDocument.model_validate(raw)

    assert migrated.schema_version == EVIDENCE_SCHEMA_VERSION


def test_grade_writes_sanitized_evidence_and_legacy_runs_are_synthesized(tmp_path: Path) -> None:
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
    )
    persisted = load_evidence(run_dir)
    encoded = json.dumps(persisted.model_dump(mode="json"))
    assert persisted.task_id == "python-cache-ttl"
    assert str(ROOT) not in encoded
    assert str(tmp_path) not in encoded
    (run_dir / "evidence.json").unlink()
    synthesized = load_evidence(run_dir)
    assert synthesized.schema_version == EVIDENCE_SCHEMA_VERSION
    assert [(item.kind, item.source) for item in synthesized.records] == [
        (item.kind, item.source) for item in persisted.records
    ]


def test_load_evidence_rejects_corrupt_document(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "result.json").write_text("{}", encoding="utf-8")
    (run / "metadata.json").write_text("{}", encoding="utf-8")
    (run / "evidence.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ReportError, match="Invalid execution evidence"):
        load_evidence(run)
