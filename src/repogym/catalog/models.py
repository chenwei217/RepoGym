"""Strict versioned catalog data without source-machine paths."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from repogym.exceptions import RepoGymError
from repogym.models import StrictModel
from repogym.security import redact_sensitive_text


class CatalogError(RepoGymError):
    """A task collection cannot satisfy its pinned contract."""


class CatalogTask(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str = Field(pattern=r"^\d+\.\d+$")
    title: str = Field(min_length=1, max_length=500)
    language: str = Field(min_length=1, max_length=100)
    difficulty: Literal["easy", "medium", "hard"]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("title", "language")
    @classmethod
    def safe_metadata(cls, value: str) -> str:
        return redact_sensitive_text(value)


class TaskCatalog(StrictModel):
    schema_version: Literal[1] = 1
    tasks: list[CatalogTask] = Field(min_length=1, max_length=10000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema version must be an integer")
        return value

    @model_validator(mode="after")
    def sorted_unique_tasks(self) -> "TaskCatalog":
        ids = [task.id for task in self.tasks]
        if ids != sorted(set(ids)):
            raise ValueError("catalog task IDs must be unique and sorted")
        return self


class CatalogIssue(StrictModel):
    task_id: str
    code: Literal[
        "missing_task", "unsafe_task", "invalid_task", "fingerprint_mismatch", "metadata_mismatch"
    ]


class CatalogVerification(StrictModel):
    schema_version: Literal[1] = 1
    checked: list[str]
    issues: list[CatalogIssue] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues
