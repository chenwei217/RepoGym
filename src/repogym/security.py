"""Path and copy helpers for untrusted task material."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import stat
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from repogym.exceptions import SecurityError
from repogym.models import TaskSpec
from repogym.privacy import REDACTED, redact_credentials, sensitive_key

MAX_SUBMISSION_FILE_BYTES = 5 * 1024 * 1024
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?<![\w>])(?:[a-z]:[\\/]|\\\\)[^\s\"'<>]*")
UNIX_ABSOLUTE_PATH = re.compile(r"(?<![:\w>])/(?:[A-Za-z_.-][^/\s\"'<>]*/)+[^\s\"'<>]*")


@dataclass(frozen=True)
class SubmissionAuditResult:
    accepted_files: list[str]
    rejected_files: list[str]
    violations: list[str]

    @property
    def accepted(self) -> bool:
        return not self.violations


def path_matches(path: str, pattern: str) -> bool:
    """Match normalized task paths with explicit recursive-directory semantics."""
    normalized = pattern.replace("\\", "/")
    if normalized.endswith("/**"):
        return path.startswith(normalized[:-3].rstrip("/") + "/")
    return fnmatch.fnmatchcase(path, normalized)


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


def _is_reparse_point(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & flag)


def _is_sensitive_submission_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    lowered = [part.casefold() for part in parts]
    if any(part in {".git", ".ssh"} for part in lowered):
        return True
    name = lowered[-1]
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in {"id_rsa", "id_ed25519", "credentials", "credentials.json", "secrets.json"}
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def submission_path_violations(
    relative: str,
    task: TaskSpec,
    size: int,
    max_file_bytes: int = MAX_SUBMISSION_FILE_BYTES,
) -> list[str]:
    """Validate one normalized submission file path without reading its contents."""
    violations: list[str] = []
    try:
        validate_relative_path(relative, "submission path")
    except SecurityError as exc:
        return [str(exc)]
    if any(path_matches(relative, pattern) for pattern in task.constraints.forbidden_paths):
        violations.append(f"Forbidden submission path: {relative}")
    if not any(path_matches(relative, pattern) for pattern in task.constraints.allowed_paths):
        violations.append(f"Submission path outside allowed scope: {relative}")
    if size > max_file_bytes:
        violations.append(
            f"Submission file exceeds {max_file_bytes} bytes: {relative} ({size} bytes)"
        )
    if _is_sensitive_submission_path(relative):
        violations.append(f"Sensitive filename is not allowed: {relative}")
    return violations


def find_case_conflicts(paths: list[str]) -> list[tuple[str, str]]:
    """Find paths that collide on case-insensitive, Unicode-normalizing filesystems."""
    seen: dict[str, str] = {}
    conflicts: list[tuple[str, str]] = []
    for path in sorted(paths):
        key = unicodedata.normalize("NFC", path).casefold()
        previous = seen.get(key)
        if previous is not None and previous != path:
            conflicts.append((previous, path))
        else:
            seen[key] = path
    return conflicts


def audit_submission(
    submission: Path,
    task: TaskSpec,
    max_file_bytes: int = MAX_SUBMISSION_FILE_BYTES,
) -> SubmissionAuditResult:
    """Audit a candidate tree without following links or reading file contents."""
    accepted_files: list[str] = []
    rejected_files: set[str] = set()
    violations: list[str] = []
    if submission.is_symlink():
        return SubmissionAuditResult([], ["."], ["Submission root may not be a symbolic link."])
    try:
        root_stat = os.lstat(submission)
    except OSError as exc:
        return SubmissionAuditResult([], ["."], [f"Cannot inspect submission root: {exc}"])
    if _is_reparse_point(root_stat):
        return SubmissionAuditResult([], ["."], ["Submission root may not be a reparse point."])
    if not stat.S_ISDIR(root_stat.st_mode):
        return SubmissionAuditResult([], ["."], ["Submission root is not a directory."])

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            relative_dir = directory.relative_to(submission).as_posix() or "."
            rejected_files.add(relative_dir)
            violations.append(f"Cannot inspect submission directory {relative_dir}: {exc}")
            return
        for entry in entries:
            item = Path(entry.path)
            relative = item.relative_to(submission).as_posix()
            try:
                item_stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                rejected_files.add(relative)
                violations.append(f"Cannot inspect submission entry {relative}: {exc}")
                continue
            if entry.is_symlink():
                rejected_files.add(relative)
                violations.append(f"Symbolic links are not allowed: {relative}")
                continue
            if _is_reparse_point(item_stat):
                rejected_files.add(relative)
                violations.append(f"Reparse points are not allowed: {relative}")
                continue
            if stat.S_ISDIR(item_stat.st_mode):
                visit(item)
                continue
            if not stat.S_ISREG(item_stat.st_mode):
                rejected_files.add(relative)
                violations.append(f"Special files are not allowed: {relative}")
                continue
            file_violations = submission_path_violations(
                relative, task, item_stat.st_size, max_file_bytes
            )
            if file_violations:
                rejected_files.add(relative)
                violations.extend(file_violations)
            else:
                accepted_files.append(relative)

    visit(submission)
    all_files = [*accepted_files, *rejected_files]
    for first, second in find_case_conflicts(all_files):
        rejected_files.update({first, second})
        accepted_files = [path for path in accepted_files if path not in {first, second}]
        violations.append(f"Case-conflicting submission paths: {first} and {second}")
    return SubmissionAuditResult(
        sorted(accepted_files), sorted(rejected_files), sorted(set(violations))
    )


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


def redact_sensitive_text(text: str, sensitive_roots: Iterable[Path | str] = ()) -> str:
    """Redact known workspaces and otherwise recognizable absolute filesystem paths."""
    redacted = redact_credentials(text)
    variants: set[str] = set()
    for root in sensitive_roots:
        value = str(root).rstrip("\\/")
        if value:
            variants.update({value, value.replace("\\", "/"), value.replace("/", "\\")})
    for value in sorted(variants, key=len, reverse=True):
        flags = re.IGNORECASE if PureWindowsPath(value).drive else 0
        redacted = re.sub(
            re.escape(value) + r"(?=$|[\\/])",
            "<WORKSPACE>",
            redacted,
            flags=flags,
        )
    redacted = re.sub(
        r"<WORKSPACE>(?:[\\/][^\s\"'<>]*)?",
        lambda match: match.group(0).replace("\\", "/"),
        redacted,
    )
    redacted = WINDOWS_ABSOLUTE_PATH.sub("<ABSOLUTE_PATH>", redacted)
    redacted = UNIX_ABSOLUTE_PATH.sub("<ABSOLUTE_PATH>", redacted)
    return redacted


def redact_value(value: Any, sensitive_roots: Iterable[Path | str] = ()) -> Any:
    """Recursively apply report redaction to JSON-compatible values."""
    roots = tuple(sensitive_roots)
    if isinstance(value, str):
        return redact_sensitive_text(value, roots)
    if isinstance(value, list):
        return [redact_value(item, roots) for item in value]
    if isinstance(value, dict):
        return {
            key: REDACTED
            if isinstance(key, str) and sensitive_key(key)
            else redact_value(item, roots)
            for key, item in value.items()
        }
    return value


def sanitize_command(command: list[str], sensitive_roots: Iterable[Path | str] = ()) -> list[str]:
    """Redact filesystem paths in command arguments while preserving relative arguments."""
    return [redact_sensitive_text(argument, sensitive_roots) for argument in command]


def redact_known_paths(text: str, paths: list[Path]) -> str:
    """Backward-compatible wrapper around unified report redaction."""
    return redact_sensitive_text(text, paths)
