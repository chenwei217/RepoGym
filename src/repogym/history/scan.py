"""Bounded non-executing inspection of persisted run directories."""

import hashlib
import json
import stat
from datetime import datetime
from pathlib import Path

from repogym.history.models import HistoryError, RunSummary, ScanDiagnostic, ScanResult
from repogym.models import GradeResult

MAX_JSON_BYTES = 4 * 1024 * 1024


def linked(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def read_json_bytes(path: Path) -> bytes:
    """Read a bounded regular file without following a final-component link."""
    if linked(path) or not path.is_file():
        raise HistoryError("Artifact must be a regular file")
    with path.open("rb") as stream:
        content = stream.read(MAX_JSON_BYTES + 1)
    if len(content) > MAX_JSON_BYTES:
        raise HistoryError("Artifact exceeds size limit")
    return content


def inspect_run(directory: Path) -> RunSummary:
    """Extract an allowlisted summary; legacy missing timestamps remain unknown."""
    try:
        if linked(directory) or not directory.is_dir():
            raise HistoryError("Run must be a non-linked directory")
        content = read_json_bytes(directory / "result.json")
        result = GradeResult.model_validate_json(content)
        if result.run_id != directory.name:
            raise HistoryError("Run ID must match its directory")
        created_at = None
        metadata_path = directory / "metadata.json"
        if metadata_path.exists() or metadata_path.is_symlink():
            metadata = json.loads(read_json_bytes(metadata_path))
            raw_time = metadata.get("created_at")
            if raw_time is not None:
                created_at = datetime.fromisoformat(raw_time)
        return RunSummary(
            run_id=result.run_id,
            task_id=result.task_id,
            status=result.status,
            score=result.score,
            duration_seconds=result.duration_seconds,
            passed=result.tests.passed,
            failed=result.tests.failed,
            created_at=created_at,
            task_fingerprint=result.task_fingerprint,
            environment_fingerprint=result.environment.fingerprint,
            result_sha256=hashlib.sha256(content).hexdigest(),
        )
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise HistoryError("Invalid run artifacts") from exc


def scan_runs(root: Path) -> ScanResult:
    """Scan direct children, isolating corrupt entries and rejecting links."""
    if not root.exists():
        raise HistoryError("Runs directory does not exist")
    if linked(root) or not root.is_dir():
        raise HistoryError("Runs root must be a non-linked directory")
    report = ScanResult()
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if linked(entry):
            report.diagnostics.append(ScanDiagnostic(entry=entry.name, code="unsafe_entry"))
        elif entry.is_dir():
            try:
                report.runs.append(inspect_run(entry))
            except HistoryError:
                report.diagnostics.append(ScanDiagnostic(entry=entry.name, code="invalid_run"))
    return report
