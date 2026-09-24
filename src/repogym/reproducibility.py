"""Deterministic task identity helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from repogym.exceptions import SecurityError
from repogym.models import TaskSpec
from repogym.security import safe_join


def task_fingerprint(task_directory: Path, task: TaskSpec) -> str:
    """Hash the complete task input surface in a stable path order."""
    task_dir = task_directory.resolve()
    roots = [
        task_dir / "task.yaml",
        safe_join(task_dir, task.description_file),
        task_dir / "starter",
        task_dir / "tests",
    ]
    files: set[Path] = set()
    for root in roots:
        if root.is_symlink():
            raise SecurityError(f"Symbolic links are not allowed in task fingerprints: {root}")
        if root.is_file():
            files.add(root)
            continue
        for path in root.rglob("*"):
            if path.is_symlink():
                raise SecurityError(f"Symbolic links are not allowed in task fingerprints: {path}")
            if path.is_file():
                files.add(path)

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(task_dir).as_posix()):
        relative = path.relative_to(task_dir).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
