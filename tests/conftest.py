from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def run_factory(tmp_path: Path) -> Callable[..., Path]:
    """Create persisted legacy-compatible runs without executing candidate code."""

    def create(run_id: str = "run-a", **changes: Any) -> Path:
        directory = tmp_path / "runs" / run_id
        directory.mkdir(parents=True)
        result = {
            "task_id": "sample-task",
            "task_fingerprint": "a" * 64,
            "run_id": run_id,
            "status": "completed",
            "score": 100,
            "dimensions": {},
            "tests": {"passed": 2, "failed": 0, "total": 2},
            "violations": [],
            "duration_seconds": 1.0,
        }
        created_at = changes.pop("created_at", "2026-01-01T00:00:00+00:00")
        result.update(changes)
        (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (directory / "metadata.json").write_text(
            json.dumps({"created_at": created_at}), encoding="utf-8"
        )
        for name in ("stdout.txt", "stderr.txt"):
            (directory / name).write_text("", encoding="utf-8")
        return directory

    return create


@pytest.fixture
def run_archive(run_factory: Callable[..., Path], tmp_path: Path) -> Path:
    from repogym.archives import export_run_archive

    path = tmp_path / "run.zip"
    export_run_archive(run_factory(), path)
    return path


@pytest.fixture
def analysis_factory(run_factory: Callable[..., Path]) -> Callable[..., Path]:
    """Build comparable synthetic observations without reading the host environment."""
    from repogym.models import RuntimeEnvironmentEvidence, RuntimeEnvironmentSnapshot

    def create(run_id: str = "run-a", **changes: Any) -> Path:
        snapshot = RuntimeEnvironmentSnapshot(
            python_implementation="CPython",
            python_version=changes.pop("python_version", "3.11.0"),
            operating_system="test",
            operating_system_release="test",
            architecture="test",
            dependencies={},
            repogym_version="0.2.0",
            executor="fixture",
        )
        environment = RuntimeEnvironmentEvidence(
            availability="available",
            snapshot=snapshot,
            fingerprint=snapshot.fingerprint(),
            reason="collected",
        )
        defaults: dict[str, Any] = {
            "candidate_fingerprint": "b" * 64,
            "environment": environment.model_dump(mode="json"),
        }
        defaults.update(changes)
        return run_factory(run_id, **defaults)

    return create


@pytest.fixture
def valid_task(tmp_path: Path) -> Path:
    task = tmp_path / "sample-task"
    (task / "starter" / "src").mkdir(parents=True)
    (task / "tests" / "public").mkdir(parents=True)
    (task / "tests" / "private").mkdir(parents=True)
    (task / "reference").mkdir()
    (task / "prompt.md").write_text("Fix it.\n", encoding="utf-8")
    (task / "starter" / "src" / "answer.py").write_text("VALUE = 0\n", encoding="utf-8")
    (task / "tests" / "public" / "test_public.py").write_text(
        "def test_public(): assert True\n", encoding="utf-8"
    )
    (task / "tests" / "private" / "test_private.py").write_text(
        "def test_private(): assert True\n", encoding="utf-8"
    )
    (task / "reference" / "solution.patch").write_text(
        "--- a/src/answer.py\n+++ b/src/answer.py\n@@ -1,1 +1,1 @@\n-VALUE = 0\n+VALUE = 1\n",
        encoding="utf-8",
    )
    (task / "task.yaml").write_text(
        """schema_version: 1
id: sample-task
title: Sample task
difficulty: easy
language: python
version: "1.0"
description_file: prompt.md
execution:
  timeout_seconds: 10
  test_command: python -m pytest -q
  working_directory: "."
scoring:
  correctness: {weight: 60}
  regression_safety: {weight: 20}
  code_quality: {weight: 10}
  scope_control: {weight: 10}
expected:
  failing_tests_before: 1
  passing_tests_after: 2
constraints:
  allowed_paths: [src/**]
  forbidden_paths: [pyproject.toml]
""",
        encoding="utf-8",
    )
    return task
