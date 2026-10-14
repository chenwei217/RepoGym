"""Deterministic, sanitized run archive creation."""

import hashlib
import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from repogym.archives.models import (
    ARTIFACTS,
    REQUIRED,
    ArchiveError,
    ArchiveFile,
    RunArchiveManifest,
)
from repogym.archives.validation import validate_contents
from repogym.evidence import EvidenceDocument
from repogym.history import HistoryError
from repogym.history.scan import inspect_run, read_json_bytes
from repogym.models import GradeResult
from repogym.security import redact_sensitive_text, redact_value


def encode_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _collect(run: Path) -> tuple[GradeResult, dict[str, bytes]]:
    inspect_run(run)
    roots = [run.resolve()]
    contents: dict[str, bytes] = {}
    for name in sorted(ARTIFACTS):
        path = run / name
        if not path.exists() and not path.is_symlink() and name not in REQUIRED:
            continue
        text = read_json_bytes(path).decode("utf-8")
        if name.endswith(".txt"):
            contents[name] = redact_sensitive_text(text, roots).encode("utf-8")
        else:
            contents[name] = encode_json(redact_value(json.loads(text), roots))
    result = GradeResult.model_validate_json(contents["result.json"])
    contents["result.json"] = encode_json(result.model_dump(mode="json"))
    if "metadata.json" in contents:
        metadata = json.loads(contents["metadata.json"])
        contents["metadata.json"] = encode_json(
            {
                "schema_version": 1,
                "created_at": metadata.get("created_at"),
                "task_fingerprint": result.task_fingerprint,
                "candidate_fingerprint": result.candidate_fingerprint,
            }
        )
    if "evidence.json" in contents:
        evidence = EvidenceDocument.model_validate_json(contents["evidence.json"])
        for record in evidence.records:
            if record.kind == "artifact" and record.source in {"stdout.txt", "stderr.txt"}:
                content = contents[record.source]
                record.details["sha256"] = hashlib.sha256(content).hexdigest()
                record.details["bytes"] = len(content)
        contents["evidence.json"] = encode_json(evidence.model_dump(mode="json"))
    return result, contents


def export_run_archive(run: Path, output: Path) -> RunArchiveManifest:
    """Publish a complete ZIP atomically without replacing an existing output."""
    temporary: Path | None = None
    try:
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise ArchiveError("Archive output exists or parent directory is missing")
        result, contents = _collect(run)
        manifest = RunArchiveManifest(
            run_id=result.run_id,
            task_id=result.task_id,
            task_fingerprint=result.task_fingerprint,
            files=[
                ArchiveFile(
                    name=name, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()
                )
                for name, data in sorted(contents.items())
            ],
        )
        validate_contents(manifest, contents)
        with tempfile.NamedTemporaryFile(
            prefix=".repogym-archive-", dir=output.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w") as archive:
            members = {"manifest.json": encode_json(manifest.model_dump(mode="json")), **contents}
            for name, content in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)
        os.link(temporary, output)
        return manifest
    except (OSError, ValueError, HistoryError) as exc:
        raise ArchiveError("Could not export run archive") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
