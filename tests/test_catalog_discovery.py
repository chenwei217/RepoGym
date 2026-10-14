from pathlib import Path

import pytest

from repogym.catalog import discover_catalog, select_tasks
from repogym.catalog.models import CatalogError

ROOT = Path(__file__).parents[1]


def test_existing_examples_are_sorted_and_selectable() -> None:
    catalog = discover_catalog(ROOT / "tasks")
    assert [task.id for task in catalog.tasks] == ["python-cache-ttl", "python-config-merge"]
    assert len(select_tasks(catalog, language="PYTHON")) == 2
    assert [task.id for task in select_tasks(catalog, query="cache")] == ["python-cache-ttl"]
    assert select_tasks(catalog, language="rust") == []
    assert all(len(task.fingerprint) == 64 for task in catalog.tasks)
    assert str(ROOT) not in catalog.model_dump_json()


def test_invalid_definitions_are_not_silently_skipped(valid_task: Path) -> None:
    invalid = valid_task.parent / "invalid-task"
    invalid.mkdir()
    (invalid / "task.yaml").write_text("not-a-mapping", encoding="utf-8")
    with pytest.raises(CatalogError, match="invalid"):
        discover_catalog(valid_task.parent)


def test_empty_missing_and_linked_roots_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CatalogError, match="No valid"):
        discover_catalog(tmp_path)
    with pytest.raises(CatalogError, match="root"):
        discover_catalog(tmp_path / "missing")
    monkeypatch.setattr("repogym.catalog.discovery.linked", lambda _: True)
    with pytest.raises(CatalogError, match="root"):
        discover_catalog(tmp_path)


def test_private_metadata_is_filtered_and_links_are_not_traversed(
    valid_task: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = valid_task / "task.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Sample task", "password=synthetic-value"),
        encoding="utf-8",
    )
    catalog = discover_catalog(valid_task.parent)
    assert "synthetic-value" not in catalog.model_dump_json()
    monkeypatch.setattr("repogym.catalog.discovery.linked", lambda p: p == valid_task)
    with pytest.raises(CatalogError, match="linked"):
        discover_catalog(valid_task.parent)
