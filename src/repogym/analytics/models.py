"""Versioned repeat-run statistics and explicit exclusion diagnostics."""

from typing import Literal

from pydantic import Field

from repogym.exceptions import RepoGymError
from repogym.models import StrictModel

CohortKey = tuple[str, str, str, str]


class AnalysisError(RepoGymError):
    """An analysis request exceeds supported input or comparison limits."""


class MetricStats(StrictModel):
    count: int = Field(ge=1)
    minimum: float
    maximum: float
    mean: float
    median: float
    p95: float


class CaseStability(StrictModel):
    id: str
    observed: int
    missing: int
    passed: int
    failed: int
    error: int
    skipped: int
    classification: Literal["stable", "variable", "insufficient"]
    duration_seconds: MetricStats | None


class CohortStats(StrictModel):
    task_id: str
    task_fingerprint: str
    candidate_fingerprint: str
    environment_fingerprint: str
    run_ids: list[str]
    run_count: int
    status_counts: dict[str, int]
    perfect_score_rate: float
    scores: MetricStats
    duration_seconds: MetricStats | None
    cases: list[CaseStability]
    warnings: list[str] = Field(default_factory=list)


class RunIssue(StrictModel):
    run_id: str
    code: Literal[
        "invalid_artifact",
        "duplicate_run",
        "conflicting_run_id",
        "cache_replay",
        "task_identity_unavailable",
        "candidate_identity_unavailable",
        "environment_unavailable",
    ]


class AnalysisReport(StrictModel):
    schema_version: Literal[1] = 1
    cohorts: list[CohortStats]
    excluded: list[RunIssue]
