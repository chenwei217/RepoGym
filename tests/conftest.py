from __future__ import annotations

from pathlib import Path

import pytest


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
        """id: sample-task
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
