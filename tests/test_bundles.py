from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from repogym.bundles import MANIFEST_NAME, export_task_bundle, import_task_bundle
from repogym.cli import app
from repogym.exceptions import BundleError
from repogym.loader import load_task
from repogym.reproducibility import task_fingerprint
from repogym.security import file_manifest


def _archive_entries(path: Path) -> list[tuple[zipfile.ZipInfo, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [(info, archive.read(info.filename)) for info in archive.infolist()]


def _rewrite_archive(
    source: Path,
    output: Path,
    transform: Callable[[list[tuple[zipfile.ZipInfo, bytes]]], list[tuple[zipfile.ZipInfo, bytes]]],
) -> None:
    with zipfile.ZipFile(output, "w") as archive:
        for info, content in transform(_archive_entries(source)):
            archive.writestr(info, content)


def _updated_manifest(
    entries: list[tuple[zipfile.ZipInfo, bytes]], path: str, content: bytes
) -> list[tuple[zipfile.ZipInfo, bytes]]:
    _, manifest_bytes = next(entry for entry in entries if entry[0].filename == MANIFEST_NAME)
    manifest: dict[str, Any] = json.loads(manifest_bytes)
    for file in manifest["files"]:
        if file["path"] == path:
            file["sha256"] = hashlib.sha256(content).hexdigest()
            file["size"] = len(content)
    rewritten = []
    for info, existing in entries:
        if info.filename == MANIFEST_NAME:
            existing = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        elif info.filename == path:
            existing = content
        rewritten.append((info, existing))
    return rewritten


def test_bundle_round_trip_preserves_task_and_fingerprint(valid_task: Path, tmp_path: Path) -> None:
    bundle = tmp_path / "sample.zip"
    manifest = export_task_bundle(valid_task, bundle)
    destination = tmp_path / "tasks"
    destination.mkdir()

    imported = import_task_bundle(bundle, destination)

    assert imported == destination / "sample-task"
    assert file_manifest(imported) == file_manifest(valid_task)
    imported_task = load_task(imported)
    assert task_fingerprint(imported, imported_task) == manifest.task_fingerprint
    with zipfile.ZipFile(bundle) as archive:
        raw_manifest = json.loads(archive.read(MANIFEST_NAME))
    paths = [file["path"] for file in raw_manifest["files"]]
    assert paths == sorted(paths)
    assert raw_manifest["format_version"] == 1
    assert set(raw_manifest["environment"]) == {
        "platform",
        "python_implementation",
        "python_version",
    }


def test_bundle_export_is_stable_in_the_same_environment(valid_task: Path, tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    export_task_bundle(valid_task, first)
    export_task_bundle(valid_task, second)
    assert first.read_bytes() == second.read_bytes()


def test_bundle_rejects_tampered_file(valid_task: Path, tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    tampered = tmp_path / "tampered.zip"
    export_task_bundle(valid_task, original)

    def alter(entries: list[tuple[zipfile.ZipInfo, bytes]]) -> list[tuple[zipfile.ZipInfo, bytes]]:
        return [
            (info, b"tampered\n" if info.filename == "prompt.md" else content)
            for info, content in entries
        ]

    _rewrite_archive(original, tampered, alter)
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="mismatch"):
        import_task_bundle(tampered, destination)
    assert not (destination / "sample-task").exists()


def test_bundle_rejects_missing_manifest_member(valid_task: Path, tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    incomplete = tmp_path / "incomplete.zip"
    export_task_bundle(valid_task, original)
    _rewrite_archive(
        original,
        incomplete,
        lambda entries: [entry for entry in entries if entry[0].filename != "prompt.md"],
    )
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="exactly match"):
        import_task_bundle(incomplete, destination)


def test_bundle_rejects_missing_or_unsupported_manifest(valid_task: Path, tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("task.yaml", b"id: sample-task\n")
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="missing manifest"):
        import_task_bundle(missing, destination)

    original = tmp_path / "original.zip"
    unsupported = tmp_path / "unsupported.zip"
    export_task_bundle(valid_task, original)

    def change_version(
        entries: list[tuple[zipfile.ZipInfo, bytes]],
    ) -> list[tuple[zipfile.ZipInfo, bytes]]:
        rewritten = []
        for info, content in entries:
            if info.filename == MANIFEST_NAME:
                manifest = json.loads(content)
                manifest["format_version"] = 2
                content = json.dumps(manifest).encode()
            rewritten.append((info, content))
        return rewritten

    _rewrite_archive(original, unsupported, change_version)
    with pytest.raises(BundleError, match="Unsupported bundle format version"):
        import_task_bundle(unsupported, destination)


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../outside.txt",
        "/absolute.txt",
        r"C:\escape.txt",
        "nested//file.txt",
        "nested/./file.txt",
        "CON.txt",
        "trailing-dot./file.txt",
    ],
)
def test_bundle_rejects_unsafe_member_paths(tmp_path: Path, unsafe_name: str) -> None:
    bundle = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(unsafe_name, b"escape")
        archive.writestr(MANIFEST_NAME, b"{}")
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="Unsafe bundle member path"):
        import_task_bundle(bundle, destination)


def test_bundle_rejects_symbolic_link_member(tmp_path: Path) -> None:
    bundle = tmp_path / "link.zip"
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(link, b"target")
        archive.writestr(MANIFEST_NAME, b"{}")
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="Symbolic links"):
        import_task_bundle(bundle, destination)


def test_bundle_rejects_directory_members_and_invalid_zip(tmp_path: Path) -> None:
    directory_bundle = tmp_path / "directory.zip"
    with zipfile.ZipFile(directory_bundle, "w") as archive:
        archive.writestr("directory/", b"")
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="directory entries"):
        import_task_bundle(directory_bundle, destination)

    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip archive")
    with pytest.raises(BundleError, match="Could not read bundle"):
        import_task_bundle(invalid, destination)


def test_bundle_rejects_case_conflicting_members(valid_task: Path, tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    conflicting = tmp_path / "conflicting.zip"
    export_task_bundle(valid_task, original)

    def add_conflict(
        entries: list[tuple[zipfile.ZipInfo, bytes]],
    ) -> list[tuple[zipfile.ZipInfo, bytes]]:
        info = zipfile.ZipInfo("PROMPT.MD")
        return [*entries, (info, b"conflict")]

    _rewrite_archive(original, conflicting, add_conflict)
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="case-conflicting"):
        import_task_bundle(conflicting, destination)


def test_bundle_validates_extracted_task_before_publish(valid_task: Path, tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    invalid = tmp_path / "invalid.zip"
    export_task_bundle(valid_task, original)
    changed_yaml = (
        (valid_task / "task.yaml").read_bytes().replace(b"id: sample-task", b"id: another-task")
    )
    _rewrite_archive(
        original,
        invalid,
        lambda entries: _updated_manifest(entries, "task.yaml", changed_yaml),
    )
    destination = tmp_path / "tasks"
    destination.mkdir()
    with pytest.raises(BundleError, match="task definition is invalid"):
        import_task_bundle(invalid, destination)
    assert list(destination.iterdir()) == []


def test_bundle_refuses_to_overwrite_outputs_and_tasks(valid_task: Path, tmp_path: Path) -> None:
    bundle = tmp_path / "task.zip"
    bundle.write_bytes(b"existing")
    with pytest.raises(BundleError, match="already exists"):
        export_task_bundle(valid_task, bundle)

    bundle.unlink()
    export_task_bundle(valid_task, bundle)
    destination = tmp_path / "tasks"
    (destination / "sample-task").mkdir(parents=True)
    with pytest.raises(BundleError, match="already exists"):
        import_task_bundle(bundle, destination)


def test_bundle_export_rejects_invalid_or_oversized_task(
    valid_task: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (valid_task / "tests" / "public" / "test_public.py").unlink()
    with pytest.raises(BundleError, match="Cannot export invalid task"):
        export_task_bundle(valid_task, tmp_path / "invalid.zip")

    (valid_task / "tests" / "public" / "test_public.py").write_text(
        "def test_public(): assert True\n", encoding="utf-8"
    )
    monkeypatch.setattr("repogym.bundles.MAX_BUNDLE_FILE_BYTES", 1)
    with pytest.raises(BundleError, match="too large"):
        export_task_bundle(valid_task, tmp_path / "oversized.zip")


def test_bundle_export_cleans_temporary_file_when_publish_fails(
    valid_task: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "task.zip"

    def fail_link(source: Path, destination: Path) -> None:
        raise OSError("publish unavailable")

    monkeypatch.setattr("repogym.bundles.os.link", fail_link)
    with pytest.raises(BundleError, match="publish unavailable"):
        export_task_bundle(valid_task, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".repogym-bundle-*"))


def test_bundle_cli_exports_imports_and_reports_errors(valid_task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    bundle = tmp_path / "sample.zip"
    exported = runner.invoke(app, ["bundle", "export", str(valid_task), str(bundle)])
    assert exported.exit_code == 0
    assert "Exported sample-task" in exported.stdout

    destination = tmp_path / "tasks"
    destination.mkdir()
    imported = runner.invoke(
        app, ["bundle", "import", str(bundle), "--destination", str(destination)]
    )
    assert imported.exit_code == 0
    assert (destination / "sample-task" / "task.yaml").is_file()

    repeated = runner.invoke(
        app, ["bundle", "import", str(bundle), "--destination", str(destination)]
    )
    assert repeated.exit_code == 1
    assert "already exists" in repeated.stderr
