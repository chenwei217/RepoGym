"""Portable, integrity-checked task packages."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from repogym.exceptions import BundleError, RepoGymError
from repogym.loader import load_task
from repogym.reproducibility import task_fingerprint, task_input_files
from repogym.security import safe_join
from repogym.validator import validate_task

BUNDLE_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_BUNDLE_FILE_BYTES = 10 * 1024 * 1024
MAX_BUNDLE_TOTAL_BYTES = 100 * 1024 * 1024
MAX_BUNDLE_FILES = 10_000
_TASK_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_WINDOWS_RESERVED = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class BundleFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class TaskBundleManifest:
    format_version: int
    task_id: str
    task_version: str
    task_fingerprint: str
    environment: dict[str, str]
    files: list[BundleFile]

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "task_id": self.task_id,
            "task_version": self.task_version,
            "task_fingerprint": self.task_fingerprint,
            "environment": self.environment,
            "files": [file.__dict__ for file in self.files],
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _environment_summary() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.system().lower(),
    }


def _validate_member_name(name: str) -> None:
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    parts = posix.parts
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or unicodedata.normalize("NFC", name) != name
        or posix.as_posix() != name
        or posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(
            part in {"", ".", ".."}
            or ":" in part
            or part.endswith((" ", "."))
            or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
            for part in parts
        )
    ):
        raise BundleError(f"Unsafe bundle member path: {name!r}")


def _validate_archive_members(infos: list[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
    if len(infos) > MAX_BUNDLE_FILES + 1:
        raise BundleError("Bundle contains too many files")
    members: dict[str, zipfile.ZipInfo] = {}
    casefolded: set[str] = set()
    total_size = 0
    for info in infos:
        if info.is_dir():
            raise BundleError(f"Bundle must not contain directory entries: {info.filename!r}")
        _validate_member_name(info.filename)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise BundleError(f"Symbolic links are not allowed in bundles: {info.filename!r}")
        limit = MAX_MANIFEST_BYTES if info.filename == MANIFEST_NAME else MAX_BUNDLE_FILE_BYTES
        if info.file_size > limit:
            raise BundleError(f"Bundle member is too large: {info.filename!r}")
        total_size += info.file_size
        if total_size > MAX_BUNDLE_TOTAL_BYTES:
            raise BundleError("Bundle uncompressed content is too large")
        collision_key = unicodedata.normalize("NFC", info.filename).casefold()
        if info.filename in members or collision_key in casefolded:
            raise BundleError(f"Duplicate or case-conflicting bundle member: {info.filename!r}")
        members[info.filename] = info
        casefolded.add(collision_key)
    return members


def _parse_manifest(raw: bytes) -> TaskBundleManifest:
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"Invalid bundle manifest: {exc}") from exc
    expected_keys = {
        "environment",
        "files",
        "format_version",
        "task_fingerprint",
        "task_id",
        "task_version",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise BundleError("Bundle manifest has an unsupported schema")
    if value["format_version"] != BUNDLE_FORMAT_VERSION:
        raise BundleError(f"Unsupported bundle format version: {value['format_version']!r}")
    task_id = value["task_id"]
    task_version = value["task_version"]
    fingerprint = value["task_fingerprint"]
    environment = value["environment"]
    entries = value["files"]
    if (
        not isinstance(task_id, str)
        or not _TASK_ID.fullmatch(task_id)
        or not isinstance(task_version, str)
        or not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        or not isinstance(environment, dict)
        or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in environment.items()
        )
        or not isinstance(entries, list)
        or not entries
    ):
        raise BundleError("Bundle manifest contains invalid values")
    files: list[BundleFile] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise BundleError("Bundle manifest file entry has an unsupported schema")
        path = entry["path"]
        digest = entry["sha256"]
        size = entry["size"]
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise BundleError("Bundle manifest file entry contains invalid values")
        _validate_member_name(path)
        files.append(BundleFile(path, digest, size))
    paths = [file.path for file in files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise BundleError("Bundle manifest files must be unique and sorted")
    return TaskBundleManifest(
        BUNDLE_FORMAT_VERSION, task_id, task_version, fingerprint, dict(environment), files
    )


def _manifest_for_task(task_directory: Path) -> tuple[TaskBundleManifest, list[tuple[str, bytes]]]:
    validation = validate_task(task_directory)
    if validation.task is None or validation.errors:
        raise BundleError("Cannot export invalid task: " + "; ".join(validation.errors))
    task = validation.task
    try:
        files = [
            (relative, path.read_bytes())
            for relative, path in task_input_files(task_directory, task)
        ]
    except OSError as exc:
        raise BundleError(f"Could not read task input: {exc}") from exc
    if len(files) > MAX_BUNDLE_FILES:
        raise BundleError("Task contains too many files for a bundle")
    total_size = 0
    for relative, content in files:
        if len(content) > MAX_BUNDLE_FILE_BYTES:
            raise BundleError(f"Task input is too large for a bundle: {relative}")
        total_size += len(content)
    if total_size > MAX_BUNDLE_TOTAL_BYTES:
        raise BundleError("Task inputs are too large for a bundle")
    manifest = TaskBundleManifest(
        BUNDLE_FORMAT_VERSION,
        task.id,
        task.version,
        task_fingerprint(task_directory, task),
        _environment_summary(),
        [BundleFile(relative, _sha256(content), len(content)) for relative, content in files],
    )
    return manifest, files


def _write_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)


def export_task_bundle(task_directory: Path, output: Path) -> TaskBundleManifest:
    """Write an atomically-published portable task archive without overwriting a file."""
    output = output.resolve()
    if output.exists() or output.is_symlink():
        raise BundleError(f"Bundle output already exists: {output}")
    if not output.parent.is_dir():
        raise BundleError(f"Bundle output directory does not exist: {output.parent}")
    manifest, files = _manifest_for_task(task_directory)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".repogym-bundle-", dir=output.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            encoded_manifest = (
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _write_member(archive, MANIFEST_NAME, encoded_manifest)
            for relative, content in files:
                _write_member(archive, relative, content)
        os.link(temporary_path, output)
    except OSError as exc:
        raise BundleError(f"Could not create bundle {output}: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return manifest


def import_task_bundle(bundle: Path, destination: Path) -> Path:
    """Verify a bundle fully, then atomically publish its task under ``destination``."""
    destination = destination.resolve()
    if not destination.is_dir():
        raise BundleError(f"Import destination does not exist: {destination}")
    try:
        with zipfile.ZipFile(bundle) as archive:
            members = _validate_archive_members(archive.infolist())
            if MANIFEST_NAME not in members:
                raise BundleError("Bundle is missing manifest.json")
            manifest = _parse_manifest(archive.read(MANIFEST_NAME))
            expected_names = {MANIFEST_NAME, *(file.path for file in manifest.files)}
            if set(members) != expected_names:
                raise BundleError("Bundle members do not exactly match its manifest")
            contents: dict[str, bytes] = {}
            for file in manifest.files:
                info = members[file.path]
                if info.file_size != file.size:
                    raise BundleError(f"Bundle size mismatch for {file.path}")
                content = archive.read(file.path)
                if _sha256(content) != file.sha256:
                    raise BundleError(f"Bundle digest mismatch for {file.path}")
                contents[file.path] = content
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise BundleError(f"Could not read bundle {bundle}: {exc}") from exc

    target = destination / manifest.task_id
    if target.exists() or target.is_symlink():
        raise BundleError(f"Import target already exists: {target}")
    try:
        staging = Path(tempfile.mkdtemp(prefix=".repogym-import-", dir=destination))
    except OSError as exc:
        raise BundleError(f"Could not create import staging directory: {exc}") from exc
    task_root = staging / manifest.task_id
    try:
        task_root.mkdir()
        for relative, content in contents.items():
            path = safe_join(task_root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        try:
            task = load_task(task_root)
        except RepoGymError as exc:
            raise BundleError(f"Bundle task definition is invalid: {exc}") from exc
        validation = validate_task(task_root)
        if validation.errors:
            raise BundleError("Bundle task validation failed: " + "; ".join(validation.errors))
        if task.version != manifest.task_version:
            raise BundleError("Bundle task version does not match its manifest")
        if task_fingerprint(task_root, task) != manifest.task_fingerprint:
            raise BundleError("Bundle task fingerprint does not match its manifest")
        os.rename(task_root, target)
    except OSError as exc:
        raise BundleError(f"Could not import bundle into {destination}: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target
