"""Path and copy helpers for untrusted task material."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

from repogym.exceptions import SecurityError


def validate_relative_path(value: str, field: str) -> None:
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if not value or posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise SecurityError(f"{field} must be a relative path: {value!r}")
    if ".." in posix.parts:
        raise SecurityError(f"{field} may not escape the task directory: {value!r}")


def safe_join(root: Path, relative: str) -> Path:
    validate_relative_path(relative, "path")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise SecurityError(f"Path escapes workspace: {relative!r}") from exc
    return candidate


def copy_tree_safe(source: Path, destination: Path) -> None:
    """Copy a tree while rejecting links and special files."""
    if not source.is_dir():
        raise SecurityError(f"Directory does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for current, directories, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            item = current_path / name
            if item.is_symlink():
                raise SecurityError(f"Symbolic links are not allowed: {item}")
        relative = current_path.relative_to(source)
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            item = current_path / filename
            if not item.is_file():
                raise SecurityError(f"Special files are not allowed: {item}")
            shutil.copy2(item, target_dir / filename)


def file_manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SecurityError(f"Symbolic links are not allowed: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
