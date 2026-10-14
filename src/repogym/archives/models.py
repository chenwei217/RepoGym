"""Version-one run archive contract and limits."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from repogym.exceptions import RepoGymError
from repogym.models import StrictModel

ARTIFACTS = frozenset(
    {
        "result.json",
        "metadata.json",
        "evidence.json",
        "changed_files.json",
        "stdout.txt",
        "stderr.txt",
    }
)
REQUIRED = frozenset({"result.json", "stdout.txt", "stderr.txt"})
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 24 * 1024 * 1024
MAX_MANIFEST_BYTES = 16384


class ArchiveError(RepoGymError):
    """A run archive could not satisfy its integrity or safety contract."""


class ArchiveFile(StrictModel):
    name: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0, le=MAX_FILE_BYTES, strict=True)


class RunArchiveManifest(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
    task_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    task_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    files: list[ArchiveFile] = Field(min_length=3, max_length=6)

    @field_validator("run_id")
    @classmethod
    def portable_run_id(cls, value: str) -> str:
        reserved = {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }
        if value.endswith(".") or value.split(".", 1)[0].casefold() in reserved:
            raise ValueError("run ID must be portable to Windows")
        return value

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema version must be an integer")
        return value

    @model_validator(mode="after")
    def members(self) -> "RunArchiveManifest":
        names = [item.name for item in self.files]
        if names != sorted(set(names)) or not REQUIRED <= set(names) <= ARTIFACTS:
            raise ValueError("archive members must be allowlisted, unique, complete and sorted")
        if sum(item.size_bytes for item in self.files) > MAX_TOTAL_BYTES:
            raise ValueError("archive content exceeds total size limit")
        return self
