"""Versioned, path-free run summaries."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from repogym.exceptions import RepoGymError
from repogym.models import StrictModel


class HistoryError(RepoGymError):
    """Invalid run inventory or query."""


class RunSummary(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
    task_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["completed", "timed_out", "cancelled", "error"]
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    created_at: datetime | None = None
    task_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    environment_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("created_at must include a timezone")
            return value.astimezone(UTC)
        return None


class RunQuery(StrictModel):
    task_id: str | None = None
    status: Literal["completed", "timed_out", "cancelled", "error"] | None = None
    min_score: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    max_score: float = Field(default=100, ge=0, le=100, allow_inf_nan=False)
    since: datetime | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_range(self) -> "RunQuery":
        if self.min_score > self.max_score:
            raise ValueError("min_score must not exceed max_score")
        if self.since is not None:
            if self.since.tzinfo is None:
                raise ValueError("since must include a timezone")
            self.since = self.since.astimezone(UTC)
        return self


class ScanDiagnostic(StrictModel):
    entry: str
    code: Literal["invalid_run", "unsafe_entry"]


class ScanResult(StrictModel):
    schema_version: Literal[1] = 1
    runs: list[RunSummary] = Field(default_factory=list)
    diagnostics: list[ScanDiagnostic] = Field(default_factory=list)
