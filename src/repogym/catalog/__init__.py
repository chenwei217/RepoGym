"""Local task curation, verification, and pinned evaluation planning."""

from repogym.catalog.discovery import discover_catalog
from repogym.catalog.manifest import load_catalog, save_catalog, verify_catalog
from repogym.catalog.selection import plan_batch, select_tasks

__all__ = [
    "discover_catalog",
    "load_catalog",
    "plan_batch",
    "save_catalog",
    "select_tasks",
    "verify_catalog",
]
