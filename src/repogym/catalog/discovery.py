"""Non-executing discovery using existing task validation and fingerprints."""

from pathlib import Path

from repogym.catalog.models import CatalogError, CatalogTask, TaskCatalog
from repogym.exceptions import RepoGymError
from repogym.history.scan import linked
from repogym.reproducibility import task_fingerprint
from repogym.security import redact_sensitive_text
from repogym.validator import validate_task


def catalog_entry(directory: Path) -> CatalogTask:
    try:
        if linked(directory) or not directory.is_dir():
            raise CatalogError("Task must be a non-linked directory")
        report = validate_task(directory)
        if report.errors or report.task is None:
            raise CatalogError("Task validation failed")
        task = report.task
        return CatalogTask(
            id=task.id,
            version=task.version,
            title=redact_sensitive_text(task.title),
            language=redact_sensitive_text(task.language),
            difficulty=task.difficulty,
            fingerprint=task_fingerprint(directory, task),
        )
    except (OSError, RepoGymError, ValueError) as exc:
        raise CatalogError("Cannot inventory invalid or unsafe task") from exc


def discover_catalog(root: Path) -> TaskCatalog:
    """Inventory all direct tasks; never silently omit malformed definitions."""
    if not root.is_dir() or linked(root):
        raise CatalogError("Tasks root must be an existing non-linked directory")
    tasks: list[CatalogTask] = []
    for directory in sorted(root.iterdir()):
        if directory.name.startswith("."):
            continue
        if directory.is_symlink() or linked(directory):
            raise CatalogError("Task root contains a linked entry")
        if directory.is_dir() and (directory / "task.yaml").exists():
            tasks.append(catalog_entry(directory))
    if not tasks:
        raise CatalogError("No valid tasks discovered")
    return TaskCatalog(tasks=tasks)
