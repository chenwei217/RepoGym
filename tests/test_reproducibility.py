from __future__ import annotations

from pathlib import Path

from repogym.loader import load_task
from repogym.reproducibility import task_fingerprint


def test_fingerprint_is_deterministic(valid_task: Path) -> None:
    task = load_task(valid_task)
    first = task_fingerprint(valid_task, task)
    second = task_fingerprint(valid_task, task)
    assert first == second
    assert len(first) == 64
    assert set(first) <= set("0123456789abcdef")


def test_fingerprint_changes_with_included_content(valid_task: Path) -> None:
    task = load_task(valid_task)
    before = task_fingerprint(valid_task, task)
    source = valid_task / "starter" / "src" / "answer.py"
    source.write_text("VALUE = 99\n", encoding="utf-8")
    assert task_fingerprint(valid_task, task) != before


def test_reference_patch_does_not_change_fingerprint(valid_task: Path) -> None:
    task = load_task(valid_task)
    before = task_fingerprint(valid_task, task)
    (valid_task / "reference" / "solution.patch").write_text("different\n", encoding="utf-8")
    assert task_fingerprint(valid_task, task) == before
