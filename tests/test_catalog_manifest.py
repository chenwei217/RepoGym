import json
from pathlib import Path

import pytest

from repogym.catalog import discover_catalog, load_catalog, save_catalog, verify_catalog
from repogym.catalog.models import CatalogError, TaskCatalog


def test_catalog_roundtrip_and_drift_diagnostics(valid_task: Path, tmp_path: Path) -> None:
    catalog = discover_catalog(valid_task.parent)
    output = tmp_path / "catalog.json"
    save_catalog(catalog, output)
    assert load_catalog(output) == catalog
    assert verify_catalog(catalog, valid_task.parent).valid
    different_metadata = TaskCatalog(
        tasks=[catalog.tasks[0].model_copy(update={"title": "Changed"})]
    )
    assert (
        verify_catalog(different_metadata, valid_task.parent).issues[0].code == "metadata_mismatch"
    )
    (valid_task / "prompt.md").write_text("Different task instructions", encoding="utf-8")
    assert verify_catalog(catalog, valid_task.parent).issues[0].code == "fingerprint_mismatch"
    (valid_task / "task.yaml").unlink()
    assert verify_catalog(catalog, valid_task.parent).issues[0].code == "invalid_task"
    valid_task.rename(valid_task.with_name("moved"))
    assert verify_catalog(catalog, valid_task.parent).issues[0].code == "missing_task"


@pytest.mark.parametrize("change", ["version", "bool", "duplicate", "path", "unknown"])
def test_bad_catalogs_have_stable_errors(valid_task: Path, tmp_path: Path, change: str) -> None:
    raw = discover_catalog(valid_task.parent).model_dump(mode="json")
    if change == "version":
        raw["schema_version"] = 2
    elif change == "bool":
        raw["schema_version"] = True
    elif change == "duplicate":
        raw["tasks"] *= 2
    elif change == "path":
        raw["tasks"][0]["id"] = "../escape"
    else:
        raw["unexpected"] = "value"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="Invalid or unsupported"):
        load_catalog(path)


def test_publication_refuses_overwrite_and_cleans_failure(
    valid_task: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = discover_catalog(valid_task.parent)
    output = tmp_path / "catalog.json"
    save_catalog(catalog, output)
    original = output.read_bytes()
    with pytest.raises(CatalogError, match="exists"):
        save_catalog(catalog, output)
    assert output.read_bytes() == original

    def fail(*args: object) -> None:
        raise PermissionError("fixture")

    monkeypatch.setattr("repogym.catalog.manifest.os.link", fail)
    with pytest.raises(CatalogError, match="publish"):
        save_catalog(catalog, tmp_path / "other.json")
    assert not list(tmp_path.glob(".repogym-catalog-*"))


def test_link_diagnostics_and_missing_root(
    valid_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = discover_catalog(valid_task.parent)
    with pytest.raises(CatalogError, match="root"):
        verify_catalog(catalog, valid_task / "missing")
    monkeypatch.setattr("repogym.catalog.manifest.linked", lambda p: p == valid_task)
    assert verify_catalog(catalog, valid_task.parent).issues[0].code == "unsafe_task"
