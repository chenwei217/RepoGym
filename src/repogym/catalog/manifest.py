"""Portable catalog serialization and drift diagnostics."""

import os
import tempfile
from pathlib import Path

from repogym.catalog.discovery import catalog_entry
from repogym.catalog.models import CatalogError, CatalogIssue, CatalogVerification, TaskCatalog
from repogym.exceptions import RepoGymError
from repogym.history.scan import linked, read_json_bytes


def publish_text(output: Path, text: str) -> None:
    """Atomically publish a new user-owned manifest without overwriting a target."""
    temporary: Path | None = None
    try:
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise CatalogError("Output exists or parent directory is missing")
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".repogym-catalog-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode("utf-8"))
        os.link(temporary, output)
    except OSError as exc:
        raise CatalogError("Could not publish catalog or batch manifest") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_catalog(catalog: TaskCatalog, output: Path) -> None:
    publish_text(output, catalog.model_dump_json(indent=2) + "\n")


def load_catalog(path: Path) -> TaskCatalog:
    try:
        return TaskCatalog.model_validate_json(read_json_bytes(path))
    except (OSError, RepoGymError, ValueError) as exc:
        raise CatalogError("Invalid or unsupported task catalog") from exc


def verify_catalog(catalog: TaskCatalog, root: Path) -> CatalogVerification:
    """Verify pinned tasks; unrelated tasks are outside a curated collection."""
    if not root.is_dir() or linked(root):
        raise CatalogError("Tasks root must be an existing non-linked directory")
    report = CatalogVerification(checked=[task.id for task in catalog.tasks])
    for expected in catalog.tasks:
        directory = root / expected.id
        if directory.is_symlink() or (directory.exists() and linked(directory)):
            report.issues.append(CatalogIssue(task_id=expected.id, code="unsafe_task"))
        elif not directory.is_dir():
            report.issues.append(CatalogIssue(task_id=expected.id, code="missing_task"))
        else:
            try:
                actual = catalog_entry(directory)
            except CatalogError:
                report.issues.append(CatalogIssue(task_id=expected.id, code="invalid_task"))
                continue
            if actual.fingerprint != expected.fingerprint:
                report.issues.append(CatalogIssue(task_id=expected.id, code="fingerprint_mismatch"))
            elif actual != expected:
                report.issues.append(CatalogIssue(task_id=expected.id, code="metadata_mismatch"))
    return report
