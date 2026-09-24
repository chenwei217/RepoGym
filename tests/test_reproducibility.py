from __future__ import annotations

from pathlib import Path

import pytest

from repogym.exceptions import FingerprintError
from repogym.loader import load_task
from repogym.reproducibility import normalize_fingerprint_path, task_fingerprint


def test_fingerprint_is_deterministic(valid_task: Path) -> None:
    task = load_task(valid_task)
    first = task_fingerprint(valid_task, task)
    second = task_fingerprint(valid_task, task)
    assert first == second
    assert len(first) == 64
    assert set(first) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    ("relative", "replacement"),
    [
        ("task.yaml", "# changed\n"),
        ("prompt.md", "Changed prompt.\n"),
        ("starter/src/answer.py", "VALUE = 99\n"),
        ("tests/public/test_public.py", "def test_changed(): assert False\n"),
        ("tests/private/test_private.py", "def test_changed(): assert False\n"),
        ("reference/solution.patch", "different\n"),
    ],
)
def test_fingerprint_changes_with_every_task_input(
    valid_task: Path, relative: str, replacement: str
) -> None:
    task = load_task(valid_task)
    before = task_fingerprint(valid_task, task)
    source = valid_task.joinpath(*relative.split("/"))
    source.write_text(replacement, encoding="utf-8")
    assert task_fingerprint(valid_task, task) != before


def test_fingerprint_ignores_mtime(valid_task: Path) -> None:
    task = load_task(valid_task)
    before = task_fingerprint(valid_task, task)
    source = valid_task / "starter" / "src" / "answer.py"
    source.touch()
    assert task_fingerprint(valid_task, task) == before


def test_fingerprint_ignores_file_creation_order(valid_task: Path) -> None:
    task = load_task(valid_task)
    first = valid_task / "starter" / "z_last.py"
    second = valid_task / "starter" / "a_first.py"
    first.write_text("Z = 1\n", encoding="utf-8")
    second.write_text("A = 1\n", encoding="utf-8")
    expected = task_fingerprint(valid_task, task)
    first.unlink()
    second.unlink()
    second.write_text("A = 1\n", encoding="utf-8")
    first.write_text("Z = 1\n", encoding="utf-8")
    assert task_fingerprint(valid_task, task) == expected


def test_fingerprint_normalizes_windows_separators() -> None:
    assert normalize_fingerprint_path(r"tests\private\test_hidden.py") == (
        "tests/private/test_hidden.py"
    )


@pytest.mark.parametrize(
    "relative",
    [
        "prompt.md",
        "starter",
        "tests/public",
        "tests/private",
        "reference/solution.patch",
    ],
)
def test_fingerprint_rejects_missing_required_input(valid_task: Path, relative: str) -> None:
    task = load_task(valid_task)
    target = valid_task.joinpath(*relative.split("/"))
    if target.is_dir():
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        target.rmdir()
    else:
        target.unlink()
    with pytest.raises(FingerprintError, match="missing required"):
        task_fingerprint(valid_task, task)
