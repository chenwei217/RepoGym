from __future__ import annotations

from pathlib import Path

import pytest

from repogym.exceptions import TaskLoadError
from repogym.loader import load_task
from repogym.models import ExecutionEvidence, ExecutionSpec, ScoringSpec
from repogym.validator import validate_task


def test_loads_valid_task(valid_task: Path) -> None:
    task = load_task(valid_task)
    assert task.id == "sample-task"
    assert task.scoring.correctness.weight == 60


def test_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(TaskLoadError, match="does not exist"):
        load_task(tmp_path / "missing")


def test_rejects_missing_yaml(tmp_path: Path) -> None:
    directory = tmp_path / "empty"
    directory.mkdir()
    with pytest.raises(TaskLoadError, match="Missing task definition"):
        load_task(directory)


@pytest.mark.parametrize("content", ["[not, a, mapping]", ": invalid"])
def test_rejects_bad_yaml(tmp_path: Path, content: str) -> None:
    directory = tmp_path / "bad"
    directory.mkdir()
    (directory / "task.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(TaskLoadError):
        load_task(directory)


def test_rejects_directory_id_mismatch(valid_task: Path) -> None:
    text = (valid_task / "task.yaml").read_text(encoding="utf-8")
    (valid_task / "task.yaml").write_text(
        text.replace("sample-task", "other-task", 1), encoding="utf-8"
    )
    with pytest.raises(TaskLoadError, match="directory name"):
        load_task(valid_task)


def test_model_rejects_bad_weight_total() -> None:
    with pytest.raises(ValueError, match="total 100"):
        ScoringSpec.model_validate(
            {
                "correctness": {"weight": 50},
                "regression_safety": {"weight": 20},
                "code_quality": {"weight": 10},
                "scope_control": {"weight": 10},
            }
        )


def test_model_rejects_blank_command() -> None:
    with pytest.raises(ValueError, match="blank"):
        ExecutionSpec(timeout_seconds=10, test_command="   ")


def test_execution_evidence_round_trips_and_reads_legacy_command() -> None:
    legacy = {
        "command": ["python", "-m", "pytest"],
        "exit_code": 0,
        "timed_out": False,
        "test_statistics_source": "pytest_summary",
    }
    evidence = ExecutionEvidence.model_validate(legacy)
    assert evidence.argv == ["python", "-m", "pytest"]
    assert evidence.command == evidence.argv
    serialized = evidence.model_dump(mode="json")
    assert "command" not in serialized
    assert serialized["working_directory"] == "<WORKSPACE>"
    assert ExecutionEvidence.model_validate(serialized) == evidence


def test_validates_complete_task(valid_task: Path) -> None:
    report = validate_task(valid_task)
    assert report.valid
    assert report.public_tests == 1
    assert report.private_tests == 1


def test_validation_reports_missing_files(valid_task: Path) -> None:
    (valid_task / "prompt.md").unlink()
    (valid_task / "tests" / "private" / "test_private.py").unlink()
    report = validate_task(valid_task)
    assert not report.valid
    assert any("prompt.md" in error for error in report.errors)
    assert any("No private" in error for error in report.errors)


def test_validation_rejects_path_escape(valid_task: Path) -> None:
    text = (valid_task / "task.yaml").read_text(encoding="utf-8")
    text = text.replace("description_file: prompt.md", "description_file: ../prompt.md")
    (valid_task / "task.yaml").write_text(text, encoding="utf-8")
    report = validate_task(valid_task)
    assert not report.valid
    assert any("escape" in error for error in report.errors)


def test_validation_detects_overlapping_constraints(valid_task: Path) -> None:
    text = (valid_task / "task.yaml").read_text(encoding="utf-8")
    text = text.replace("forbidden_paths: [pyproject.toml]", "forbidden_paths: [src/private/**]")
    (valid_task / "task.yaml").write_text(text, encoding="utf-8")
    report = validate_task(valid_task)
    assert any("conflict" in error for error in report.errors)
