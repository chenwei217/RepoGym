"""Task selection and relative, fingerprint-pinned batch planning."""

import os
from pathlib import Path

from repogym.batch import BatchJobSpec, BatchManifest
from repogym.catalog.manifest import verify_catalog
from repogym.catalog.models import CatalogError, CatalogTask, TaskCatalog
from repogym.history.scan import linked


def select_tasks(
    catalog: TaskCatalog,
    *,
    language: str | None = None,
    difficulty: str | None = None,
    query: str = "",
) -> list[CatalogTask]:
    """Search catalog metadata offline, retaining lexical task order."""
    return [
        task
        for task in catalog.tasks
        if (language is None or task.language.casefold() == language.casefold())
        and (difficulty is None or task.difficulty == difficulty)
        and query.casefold() in f"{task.id} {task.title}".casefold()
    ]


def plan_batch(
    catalog: TaskCatalog, tasks_root: Path, submissions_root: Path, output: Path
) -> BatchManifest:
    """Plan one job per task using submissions/<task-id>; execute nothing."""
    if not verify_catalog(catalog, tasks_root).valid:
        raise CatalogError("Pinned catalog has drift; batch planning refused")
    if not submissions_root.is_dir() or linked(submissions_root):
        raise CatalogError("Submissions root must be an existing non-linked directory")
    jobs: list[BatchJobSpec] = []
    for task in catalog.tasks:
        submission = submissions_root / task.id
        if not submission.is_dir() or linked(submission):
            raise CatalogError(f"Missing or unsafe submission for {task.id}")
        try:
            task_path = Path(
                os.path.relpath((tasks_root / task.id).resolve(), output.parent.resolve())
            )
            submission_path = Path(os.path.relpath(submission.resolve(), output.parent.resolve()))
        except ValueError as exc:
            raise CatalogError(
                "Batch manifest must share a filesystem drive with its inputs"
            ) from exc
        jobs.append(
            BatchJobSpec(
                id=task.id,
                task=task_path.as_posix(),
                submission=submission_path.as_posix(),
                task_fingerprint=task.fingerprint,
            )
        )
    return BatchManifest(schema_version=1, jobs=jobs)
