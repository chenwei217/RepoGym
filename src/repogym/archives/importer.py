"""Verified same-filesystem archive import with exclusive publication."""

import os
import shutil
import tempfile
from pathlib import Path

from repogym.archives.models import ArchiveError
from repogym.archives.validation import read_run_archive
from repogym.history import HistoryError
from repogym.history.scan import inspect_run, linked


def import_run_archive(archive: Path, destination: Path) -> Path:
    """Validate before staging and publish a new run without overwriting an existing one."""
    manifest, contents = read_run_archive(archive)
    if not destination.is_dir() or linked(destination):
        raise ArchiveError("Destination must be an existing non-linked directory")
    target = destination / manifest.run_id
    lock = destination / f".import-{manifest.run_id}.lock"
    staging: Path | None = None
    acquired = False
    try:
        with lock.open("x"):
            acquired = True
        if target.exists() or target.is_symlink():
            raise ArchiveError("Import target already exists")
        staging = Path(tempfile.mkdtemp(prefix=".repogym-archive-", dir=destination))
        prepared = staging / manifest.run_id
        prepared.mkdir()
        for name, content in contents.items():
            (prepared / name).write_bytes(content)
        inspect_run(prepared)
        os.rename(prepared, target)
        return target
    except (OSError, HistoryError) as exc:
        raise ArchiveError(
            "Could not publish run; destination or import lock is unavailable"
        ) from exc
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        if acquired:
            lock.unlink(missing_ok=True)
