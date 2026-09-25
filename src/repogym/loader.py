"""Task specification loading."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from repogym.exceptions import TaskLoadError
from repogym.models import TaskSpec
from repogym.spec_schema import migrate_task_spec


def task_from_mapping(raw: Any, task_directory: Path) -> TaskSpec:
    """Validate a loader-produced mapping against the current TaskSpec contract."""
    task_dir = task_directory.resolve()
    if not isinstance(raw, Mapping):
        raise TaskLoadError("Task loader must return a mapping")
    raw = migrate_task_spec(dict(raw))
    try:
        task = TaskSpec.model_validate(raw)
    except PydanticValidationError as exc:
        messages = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            messages.append(f"{location}: {error['msg']}")
        raise TaskLoadError("Invalid task.yaml:\n  - " + "\n  - ".join(messages)) from exc
    if task.id != task_dir.name:
        raise TaskLoadError(f"task id {task.id!r} must match directory name {task_dir.name!r}")
    return task


def load_task(task_directory: Path) -> TaskSpec:
    task_dir = task_directory.resolve()
    config_path = task_dir / "task.yaml"
    if not task_dir.is_dir():
        raise TaskLoadError(f"Task directory does not exist: {task_directory}")
    if not config_path.is_file():
        raise TaskLoadError(f"Missing task definition: {config_path}")
    try:
        raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise TaskLoadError(f"Could not read task.yaml: {exc}") from exc
    if not isinstance(raw, dict):
        raise TaskLoadError("task.yaml must contain a YAML mapping")
    return task_from_mapping(raw, task_dir)
