"""Content-addressed, atomically published execution cache."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repogym import __version__
from repogym.commands import resolve_command
from repogym.exceptions import CacheError
from repogym.models import CacheEvidence, TaskSpec
from repogym.security import file_manifest

CACHE_SCHEMA_VERSION = 1
MANIFEST_NAME = "cache-manifest.json"
_WINDOWS = os.name == "nt"


@dataclass(frozen=True)
class CacheEntryInfo:
    key: str
    valid: bool
    size_bytes: int
    error: str | None = None


def _publish_directory(source: Path, target: Path) -> None:
    """Atomically rename a directory, retrying transient Windows scanner locks."""
    delay = 0.01
    for attempt in range(8):
        try:
            os.rename(source, target)
            return
        except PermissionError:
            if not _WINDOWS or attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def build_cache_key(
    task: TaskSpec,
    task_fingerprint: str,
    submission: Path,
    executor_identity: str,
    environment_fingerprint: str | None = None,
) -> str:
    """Hash every task, input, command, runtime, and RepoGym compatibility input."""
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "repogym_version": __version__,
        "task_fingerprint": task_fingerprint,
        "submission_files": file_manifest(submission),
        "command": resolve_command(task.execution.test_command),
        "executor": executor_identity,
        "environment_fingerprint": environment_fingerprint,
        "environment": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExecutionCache:
    """Manage versioned cache entries and per-key process locks."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.version_root = self.root / f"v{CACHE_SCHEMA_VERSION}"
        self.entries = self.version_root / "entries"
        self.locks = self.version_root / "locks"

    @staticmethod
    def _validate_key(key: str) -> None:
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise CacheError(f"Invalid cache key: {key!r}")

    def _entry_path(self, key: str) -> Path:
        self._validate_key(key)
        return self.entries / key

    @contextmanager
    def lock(
        self,
        key: str,
        timeout_seconds: float = 30,
        stale_after_seconds: float = 3600,
    ) -> Iterator[None]:
        """Acquire a portable exclusive file lock for one cache key."""
        self._validate_key(key)
        self.locks.mkdir(parents=True, exist_ok=True)
        path = self.locks / f"{key}.lock"
        owner = uuid.uuid4().hex
        deadline = time.monotonic() + timeout_seconds
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > stale_after_seconds:
                    with suppress(FileNotFoundError):
                        path.unlink()
                    continue
                if time.monotonic() >= deadline:
                    raise CacheError(f"Timed out waiting for cache key {key}") from None
                time.sleep(0.05)
        try:
            payload = json.dumps(
                {"owner": owner, "pid": os.getpid(), "created_at": time.time()}
            ).encode("ascii")
            os.write(descriptor, payload)
            os.close(descriptor)
            descriptor = None
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                lock_data = json.loads(path.read_text(encoding="ascii"))
                if lock_data.get("owner") == owner:
                    path.unlink()
            except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
                pass

    @staticmethod
    def _hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _validate_entry(self, key: str) -> tuple[dict[str, Any], int]:
        entry = self._entry_path(key)
        manifest_path = entry / MANIFEST_NAME
        try:
            manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest must be an object")
            if manifest.get("schema_version") != CACHE_SCHEMA_VERSION:
                raise ValueError("unsupported manifest schema")
            if manifest.get("key") != key:
                raise ValueError("manifest key mismatch")
            files = manifest.get("files")
            if not isinstance(files, dict) or not files:
                raise ValueError("manifest files must be a nonempty object")
            declared = set(files)
            actual = {path.name for path in entry.iterdir() if path.name != MANIFEST_NAME}
            if declared != actual:
                raise ValueError("cache entry membership mismatch")
            size = manifest_path.stat().st_size
            for name, expected_hash in files.items():
                if not isinstance(name, str) or Path(name).name != name:
                    raise ValueError("cache artifact name is unsafe")
                if not isinstance(expected_hash, str):
                    raise ValueError("cache artifact hash is invalid")
                artifact = entry / name
                if artifact.is_symlink() or not artifact.is_file():
                    raise ValueError(f"cache artifact is not a regular file: {name}")
                size += artifact.stat().st_size
                if self._hash(artifact) != expected_hash:
                    raise ValueError(f"cache artifact hash mismatch: {name}")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise CacheError(f"Invalid cache entry {key}: {exc}") from exc
        return manifest, size

    def inspect(self) -> list[CacheEntryInfo]:
        if not self.entries.is_dir():
            return []
        result: list[CacheEntryInfo] = []
        for entry in sorted(self.entries.iterdir(), key=lambda path: path.name):
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            try:
                _, size = self._validate_entry(entry.name)
            except CacheError as exc:
                result.append(CacheEntryInfo(entry.name, False, 0, str(exc)))
            else:
                result.append(CacheEntryInfo(entry.name, True, size))
        return result

    def recover(self, key: str) -> bool:
        """Remove one corrupt entry and report whether a valid entry remains."""
        entry = self._entry_path(key)
        if not entry.exists():
            return False
        try:
            self._validate_entry(key)
        except CacheError:
            shutil.rmtree(entry)
            return False
        return True

    def store(self, key: str, run_directory: Path) -> None:
        """Publish a complete run using an atomic directory rename."""
        target = self._entry_path(key)
        if target.exists():
            return
        self.entries.mkdir(parents=True, exist_ok=True)
        temporary = self.entries / f".{key}.{uuid.uuid4().hex}.tmp"
        temporary.mkdir()
        try:
            files: dict[str, str] = {}
            for source in sorted(run_directory.iterdir(), key=lambda path: path.name):
                if source.is_symlink() or not source.is_file():
                    raise CacheError(f"Run artifact is not a regular file: {source.name}")
                destination = temporary / source.name
                shutil.copyfile(source, destination)
                files[source.name] = self._hash(destination)
            manifest = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "key": key,
                "files": files,
            }
            (temporary / MANIFEST_NAME).write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _publish_directory(temporary, target)
        except FileExistsError:
            shutil.rmtree(temporary, ignore_errors=True)
        except (OSError, CacheError) as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Could not publish cache entry {key}: {exc}") from exc

    def restore(self, key: str, output_root: Path, run_id: str) -> Path | None:
        """Materialize a validated entry as a distinct replay run."""
        entry = self._entry_path(key)
        if not entry.exists():
            return None
        try:
            manifest, _ = self._validate_entry(key)
        except CacheError:
            shutil.rmtree(entry)
            return None
        output_root = output_root.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = output_root / f".{run_id}.{uuid.uuid4().hex}.tmp"
        target = output_root / run_id
        temporary.mkdir()
        try:
            for name in sorted(manifest["files"]):
                shutil.copyfile(entry / name, temporary / name)
            result_path = temporary / "result.json"
            metadata_path = temporary / "metadata.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            source_run_id = str(result["run_id"])
            cache = CacheEvidence(key=key, hit=True, source_run_id=source_run_id)
            result["run_id"] = run_id
            result["cache"] = cache.model_dump(mode="json")
            metadata["created_at"] = datetime.now(UTC).isoformat()
            metadata["cache"] = cache.model_dump(mode="json")
            result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            _publish_directory(temporary, target)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            raise CacheError(f"Could not restore cache entry {key}: {exc}") from exc
        return target

    def clear(self) -> int:
        """Remove the snapshot of entries present when clearing begins."""
        if not self.entries.is_dir():
            return 0
        keys = sorted(path.name for path in self.entries.iterdir() if path.is_dir())
        removed = 0
        for key in keys:
            try:
                self._validate_key(key)
            except CacheError:
                continue
            with self.lock(key):
                entry = self._entry_path(key)
                if entry.exists():
                    shutil.rmtree(entry)
                    removed += 1
        return removed
