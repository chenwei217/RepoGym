"""Version negotiation and migrations for task definitions."""

from __future__ import annotations

from typing import Any

from repogym.exceptions import TaskLoadError

CURRENT_TASK_SCHEMA_VERSION = 1
LEGACY_TASK_SCHEMA_VERSION = 0
SUPPORTED_TASK_SCHEMA_VERSIONS = (LEGACY_TASK_SCHEMA_VERSION, CURRENT_TASK_SCHEMA_VERSION)


def migrate_task_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a current-schema copy of a task mapping.

    Definitions written before schema versioning omitted ``schema_version`` and
    are treated as version 0. Version 0 and explicit version 0 currently share
    the same fields, so the migration records version 1 without altering the
    task's meaning.
    """
    migrated = dict(raw)
    version = migrated.get("schema_version", LEGACY_TASK_SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        raise TaskLoadError("Invalid task schema version: expected an integer")
    if version not in SUPPORTED_TASK_SCHEMA_VERSIONS:
        supported = ", ".join(str(item) for item in SUPPORTED_TASK_SCHEMA_VERSIONS)
        raise TaskLoadError(
            f"Unsupported task schema version: {version}; supported versions: {supported}"
        )
    if version == LEGACY_TASK_SCHEMA_VERSION:
        migrated["schema_version"] = CURRENT_TASK_SCHEMA_VERSION
    return migrated
