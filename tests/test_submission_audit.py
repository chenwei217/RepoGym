from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from repogym.exceptions import SecurityError
from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.models import ExecutionResult
from repogym.security import (
    _is_reparse_point,
    audit_submission,
    find_case_conflicts,
    submission_path_violations,
)


class FailingIfCalledExecutor:
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        raise AssertionError("submission audit failure must prevent execution")


def test_audit_accepts_only_in_scope_regular_files(valid_task: Path, tmp_path: Path) -> None:
    submission = tmp_path / "submission"
    (submission / "src").mkdir(parents=True)
    (submission / "src" / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    result = audit_submission(submission, load_task(valid_task))
    assert result.accepted
    assert result.accepted_files == ["src/answer.py"]
    assert result.rejected_files == []


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("../escape.py", "may not escape"),
        ("pyproject.toml", "Forbidden submission path"),
        ("docs/note.md", "outside allowed scope"),
        ("src/.env", "Sensitive filename"),
        ("src/private.pem", "Sensitive filename"),
    ],
)
def test_submission_path_policy(valid_task: Path, relative: str, message: str) -> None:
    violations = submission_path_violations(relative, load_task(valid_task), size=1)
    assert any(message in violation for violation in violations)


def test_audit_rejects_oversized_file(valid_task: Path, tmp_path: Path) -> None:
    submission = tmp_path / "submission"
    (submission / "src").mkdir(parents=True)
    (submission / "src" / "answer.py").write_text("large", encoding="utf-8")
    result = audit_submission(submission, load_task(valid_task), max_file_bytes=1)
    assert not result.accepted
    assert result.rejected_files == ["src/answer.py"]
    assert "exceeds 1 bytes" in result.violations[0]


def test_case_conflicts_are_deterministic() -> None:
    assert find_case_conflicts(["src/Answer.py", "src/answer.py", "src/other.py"]) == [
        ("src/Answer.py", "src/answer.py")
    ]


def test_reparse_attribute_is_detected() -> None:
    result = SimpleNamespace(st_file_attributes=0x400)
    assert _is_reparse_point(result)  # type: ignore[arg-type]


def test_audit_does_not_read_accepted_file_contents(
    valid_task: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    submission = tmp_path / "submission"
    (submission / "src").mkdir(parents=True)
    (submission / "src" / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")

    def fail_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("audit must not read submission contents")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    assert audit_submission(submission, load_task(valid_task)).accepted


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks may require Windows privileges")
def test_audit_rejects_symlink_without_following_it(valid_task: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    submission = tmp_path / "submission"
    (submission / "src").mkdir(parents=True)
    (submission / "src" / "link.py").symlink_to(outside)
    result = audit_submission(submission, load_task(valid_task))
    assert not result.accepted
    assert result.rejected_files == ["src/link.py"]
    assert "Symbolic links" in result.violations[0]


def test_grade_stops_before_execution_when_audit_fails(valid_task: Path, tmp_path: Path) -> None:
    submission = tmp_path / "submission"
    submission.mkdir()
    (submission / "pyproject.toml").write_text("forbidden", encoding="utf-8")
    with pytest.raises(SecurityError, match="Submission audit failed"):
        grade_submission(
            valid_task,
            submission,
            tmp_path / "runs",
            FailingIfCalledExecutor(),
        )
    assert not (tmp_path / "runs").exists()
