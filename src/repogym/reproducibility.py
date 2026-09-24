"""Deterministic task identity helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from repogym.exceptions import FingerprintError, SecurityError
from repogym.models import TaskSpec
from repogym.security import safe_join


def normalize_fingerprint_path(path: str) -> str:
    """Return a platform-independent path for fingerprint manifests."""
    return path.replace("\\", "/")


def task_fingerprint(task_directory: Path, task: TaskSpec) -> str:
    """Hash the complete task input surface in a stable path order."""
    task_dir = task_directory.resolve()
    required_roots = [
        (task_dir / "task.yaml", "file"),
        (task_dir / "prompt.md", "file"),
        (safe_join(task_dir, task.description_file), "file"),
        (task_dir / "starter", "directory"),
        (task_dir / "tests" / "public", "directory"),
        (task_dir / "tests" / "private", "directory"),
        (task_dir / "reference" / "solution.patch", "file"),
    ]
    files: set[Path] = set()
    for root, expected_kind in required_roots:
        if root.is_symlink():
            raise SecurityError(f"Symbolic links are not allowed in task fingerprints: {root}")
        exists_as_expected = root.is_file() if expected_kind == "file" else root.is_dir()
        if not exists_as_expected:
            missing_relative = normalize_fingerprint_path(str(root.relative_to(task_dir)))
            raise FingerprintError(
                f"Cannot fingerprint task: missing required {expected_kind} {missing_relative}"
            )
        if expected_kind == "file":
            files.add(root)
            continue
        for path in root.rglob("*"):
            if path.is_symlink():
                raise SecurityError(f"Symbolic links are not allowed in task fingerprints: {path}")
            if path.is_file():
                files.add(path)

    digest = hashlib.sha256()
    for path in sorted(
        files,
        key=lambda item: normalize_fingerprint_path(str(item.relative_to(task_dir))),
    ):
        relative_text = normalize_fingerprint_path(str(path.relative_to(task_dir)))
        relative_bytes = relative_text.encode("utf-8")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise FingerprintError(f"Cannot fingerprint task file {relative_text}: {exc}") from exc
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
