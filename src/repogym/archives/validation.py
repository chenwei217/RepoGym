"""Fail-closed archive decoding, integrity checks, and cross-artifact validation."""

import hashlib
import json
import stat
import zipfile
from datetime import datetime
from pathlib import Path

from repogym.archives.models import (
    ARTIFACTS,
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES,
    ArchiveError,
    RunArchiveManifest,
)
from repogym.evidence import EvidenceDocument
from repogym.exceptions import SecurityError
from repogym.history.models import RunSummary
from repogym.models import GradeResult
from repogym.security import redact_sensitive_text, redact_value, validate_relative_path


def validate_contents(manifest: RunArchiveManifest, contents: dict[str, bytes]) -> None:
    """Validate hashes, source associations, models, and diagnostic privacy."""
    try:
        if set(contents) != {entry.name for entry in manifest.files}:
            raise ArchiveError("Archive members do not match manifest")
        for entry in manifest.files:
            content = contents[entry.name]
            if (
                len(content) != entry.size_bytes
                or hashlib.sha256(content).hexdigest() != entry.sha256
            ):
                raise ArchiveError("Archive artifact hash or size mismatch")
            text = content.decode("utf-8")
            safe = (
                redact_value(json.loads(text)) == json.loads(text)
                if entry.name.endswith(".json")
                else redact_sensitive_text(text) == text
            )
            if not safe:
                raise ArchiveError("Archive contains unredacted diagnostics")
        raw_result = json.loads(contents["result.json"])
        if redact_value(raw_result) != raw_result:
            raise ArchiveError("Archive contains sensitive structured values")
        result = GradeResult.model_validate(raw_result)
        if (result.run_id, result.task_id, result.task_fingerprint) != (
            manifest.run_id,
            manifest.task_id,
            manifest.task_fingerprint,
        ):
            raise ArchiveError("Archive result identity does not match manifest")
        created_at = None
        if "metadata.json" in contents:
            metadata = json.loads(contents["metadata.json"])
            if not isinstance(metadata, dict) or set(metadata) - {
                "schema_version",
                "created_at",
                "task_fingerprint",
            }:
                raise ArchiveError("Unsupported archived metadata")
            if metadata.get("schema_version") != 1:
                raise ArchiveError("Unsupported archived metadata version")
            if metadata.get("task_fingerprint") != result.task_fingerprint:
                raise ArchiveError("Metadata fingerprint does not match result")
            if metadata.get("created_at") is not None:
                created_at = datetime.fromisoformat(metadata["created_at"])
        RunSummary(
            run_id=result.run_id,
            task_id=result.task_id,
            status=result.status,
            score=result.score,
            passed=result.tests.passed,
            failed=result.tests.failed,
            duration_seconds=result.duration_seconds,
            created_at=created_at,
            result_sha256=hashlib.sha256(contents["result.json"]).hexdigest(),
        )
        if "changed_files.json" in contents:
            changed = json.loads(contents["changed_files.json"])
            if not isinstance(changed, list) or any(not isinstance(p, str) for p in changed):
                raise ArchiveError("Invalid changed-file inventory")
            for path in changed:
                validate_relative_path(path, "changed file")
        if "evidence.json" in contents:
            evidence = EvidenceDocument.model_validate_json(contents["evidence.json"])
            if (
                evidence.task_id != result.task_id
                or evidence.task_fingerprint != result.task_fingerprint
            ):
                raise ArchiveError("Evidence task association does not match result")
            for record in evidence.records:
                if record.task_id != result.task_id:
                    raise ArchiveError("Evidence record belongs to a different task")
                if record.kind == "artifact" and record.source in {"stdout.txt", "stderr.txt"}:
                    content = contents[record.source]
                    if record.details.get("sha256") != hashlib.sha256(
                        content
                    ).hexdigest() or record.details.get("bytes") != len(content):
                        raise ArchiveError("Evidence output digest does not match artifact")
    except (ValueError, TypeError, KeyError, AttributeError, SecurityError) as exc:
        raise ArchiveError("Invalid archive schema or run artifacts") from exc


def read_run_archive(path: Path) -> tuple[RunArchiveManifest, dict[str, bytes]]:
    """Decode bounded flat members; never extract paths supplied by an archive."""
    try:
        if path.stat().st_size > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES + 16384:
            raise ArchiveError("Archive exceeds compressed size limit")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or not 4 <= len(names) <= 7:
                raise ArchiveError("Duplicate or invalid archive member count")
            if "manifest.json" not in names or set(names) - {"manifest.json", *ARTIFACTS}:
                raise ArchiveError("Unsafe or unknown archive members")
            total = 0
            for info in infos:
                mode = stat.S_IFMT(info.external_attr >> 16)
                limit = MAX_MANIFEST_BYTES if info.filename == "manifest.json" else MAX_FILE_BYTES
                if info.is_dir() or mode not in (0, stat.S_IFREG) or info.flag_bits & 1:
                    raise ArchiveError("Links, special files and encrypted members are not allowed")
                if info.file_size > limit:
                    raise ArchiveError("Archive member exceeds size limit")
                total += info.file_size
            if total > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES:
                raise ArchiveError("Archive exceeds uncompressed size limit")
            manifest = RunArchiveManifest.model_validate_json(archive.read("manifest.json"))
            contents = {name: archive.read(name) for name in names if name != "manifest.json"}
        validate_contents(manifest, contents)
        return manifest, contents
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise ArchiveError("Cannot decode run archive") from exc


def verify_run_archive(path: Path) -> RunArchiveManifest:
    """Check all artifacts without writing or executing anything."""
    return read_run_archive(path)[0]
