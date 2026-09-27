"""Validated task and result models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionSpec(StrictModel):
    timeout_seconds: int = Field(ge=1, le=600)
    test_command: str = Field(min_length=1)
    working_directory: str = "."

    @field_validator("test_command")
    @classmethod
    def command_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ScoreWeight(StrictModel):
    weight: int = Field(ge=0, le=100)


class ScoringSpec(StrictModel):
    correctness: ScoreWeight
    regression_safety: ScoreWeight
    code_quality: ScoreWeight
    scope_control: ScoreWeight

    @model_validator(mode="after")
    def weights_total_100(self) -> ScoringSpec:
        total = sum(
            (
                self.correctness.weight,
                self.regression_safety.weight,
                self.code_quality.weight,
                self.scope_control.weight,
            )
        )
        if total != 100:
            raise ValueError(f"scoring weights must total 100, got {total}")
        return self


class ExpectedSpec(StrictModel):
    failing_tests_before: int = Field(ge=1)
    passing_tests_after: int = Field(ge=1)


class ConstraintSpec(StrictModel):
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)


class TaskSpec(StrictModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    language: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+$")
    description_file: str
    execution: ExecutionSpec
    scoring: ScoringSpec
    expected: ExpectedSpec
    constraints: ConstraintSpec


class TestCaseResult(StrictModel):
    id: str = Field(min_length=1)
    status: Literal["passed", "failed", "error", "skipped"]
    duration_seconds: float = Field(ge=0)
    failure_summary: str | None = Field(default=None, max_length=1000)
    output_refs: list[Literal["stdout.txt", "stderr.txt"]] = Field(default_factory=list)


class TestCaseEvidence(StrictModel):
    schema_version: Literal[1] = 1
    availability: Literal["available", "unavailable"]
    source: Literal["pytest_junit", "unavailable"]
    reason: str = Field(min_length=1)
    cases: list[TestCaseResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_state_and_order(self) -> TestCaseEvidence:
        if self.availability == "available":
            if self.source != "pytest_junit" or self.reason != "collected":
                raise ValueError("available test evidence must be collected from pytest_junit")
        elif self.source != "unavailable" or self.cases:
            raise ValueError("unavailable test evidence cannot contain test cases")
        ids = [case.id for case in self.cases]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("test case ids must be unique and sorted")
        return self

    @classmethod
    def unavailable(cls, reason: str) -> TestCaseEvidence:
        return cls(availability="unavailable", source="unavailable", reason=reason)


class ExecutionResult(BaseModel):
    command: list[str]
    return_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False
    termination_diagnostics: list[str] = Field(default_factory=list)
    stdout_bytes: int = Field(default=0, ge=0)
    stderr_bytes: int = Field(default=0, ge=0)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    test_evidence: TestCaseEvidence | None = None


class TestCounts(BaseModel):
    passed: int = 0
    failed: int = 0
    total: int = 0


class DimensionResult(BaseModel):
    score: float
    max_score: int
    reason: str


class ExecutionEvidence(BaseModel):
    argv: list[str] = Field(default_factory=list)
    exit_code: int | None
    timed_out: bool
    cancelled: bool = False
    duration_seconds: float = Field(default=0.0, ge=0)
    working_directory: Literal["<WORKSPACE>"] = "<WORKSPACE>"
    stdout_file: Literal["stdout.txt"] = "stdout.txt"
    stderr_file: Literal["stderr.txt"] = "stderr.txt"
    test_statistics_source: Literal["pytest_junit", "pytest_summary", "unavailable"]
    termination_diagnostics: list[str] = Field(default_factory=list)
    stdout_bytes: int = Field(default=0, ge=0)
    stderr_bytes: int = Field(default=0, ge=0)
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_command(cls, value: Any) -> Any:
        """Read schema-v1 results that stored argv under ``command``."""
        if isinstance(value, dict) and "argv" not in value and "command" in value:
            migrated = dict(value)
            migrated["argv"] = migrated["command"]
            return migrated
        return value

    @property
    def command(self) -> list[str]:
        """Compatibility accessor for callers that used the schema-v1 name."""
        return self.argv


class CacheEvidence(BaseModel):
    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    hit: bool
    source_run_id: str | None = None


class GradeResult(BaseModel):
    task_id: str
    task_fingerprint: str | None = None
    run_id: str
    status: Literal["completed", "timed_out", "cancelled", "error"]
    score: float
    dimensions: dict[str, DimensionResult]
    tests: TestCounts
    violations: list[str]
    duration_seconds: float
    execution: ExecutionEvidence | None = None
    cache: CacheEvidence | None = None
    test_evidence: TestCaseEvidence = Field(
        default_factory=lambda: TestCaseEvidence.unavailable("legacy_run")
    )
