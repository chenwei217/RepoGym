import hashlib
import json
import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from repogym.archives import verify_run_archive
from repogym.archives.models import ArchiveError


def _rewrite(path: Path, members: list[tuple[str | zipfile.ZipInfo, bytes]]) -> None:
    with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as archive:
        warnings.simplefilter("ignore", UserWarning)
        for name, content in members:
            archive.writestr(name, content)


def _members(path: Path) -> list[tuple[str | zipfile.ZipInfo, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [(info.filename, archive.read(info)) for info in archive.infolist()]


@pytest.mark.parametrize(
    "extra",
    [
        "../escape",
        "C:/escape",
        "folder/file",
        "RESULT.JSON",
        "./result.json",
        "result.json",
        "unknown.txt",
    ],
)
def test_unsafe_and_duplicate_members(run_archive: Path, extra: str) -> None:
    _rewrite(run_archive, [*_members(run_archive), (extra, b"x")])
    with pytest.raises(ArchiveError):
        verify_run_archive(run_archive)


def test_missing_member_and_hash_tampering(run_archive: Path) -> None:
    members = _members(run_archive)
    _rewrite(run_archive, [(n, b"tampered" if n == "stdout.txt" else b) for n, b in members])
    with pytest.raises(ArchiveError, match="mismatch"):
        verify_run_archive(run_archive)
    _rewrite(run_archive, [(n, b) for n, b in members if n != "stdout.txt"])
    with pytest.raises(ArchiveError):
        verify_run_archive(run_archive)


@pytest.mark.parametrize("version", [True, 2, "1"])
def test_schema_versions_are_strict(run_archive: Path, version: object) -> None:
    members = _members(run_archive)
    raw = json.loads(dict(members)["manifest.json"])
    raw["schema_version"] = version
    _rewrite(
        run_archive,
        [(n, json.dumps(raw).encode() if n == "manifest.json" else b) for n, b in members],
    )
    with pytest.raises(ArchiveError):
        verify_run_archive(run_archive)


def test_zip_link_and_size_limits(run_archive: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    members = _members(run_archive)
    link = zipfile.ZipInfo("stdout.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    _rewrite(run_archive, [(link if n == "stdout.txt" else n, b) for n, b in members])
    with pytest.raises(ArchiveError, match="Links"):
        verify_run_archive(run_archive)
    _rewrite(run_archive, members)
    monkeypatch.setattr("repogym.archives.validation.MAX_FILE_BYTES", 8)
    with pytest.raises(ArchiveError, match="size limit"):
        verify_run_archive(run_archive)


def test_rehashed_secrets_and_changed_identity_are_rejected(run_archive: Path) -> None:
    members = dict(_members(run_archive))
    members["stdout.txt"] = b"password=synthetic-value"
    manifest = json.loads(members["manifest.json"])
    for entry in manifest["files"]:
        data = members[entry["name"]]
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["size_bytes"] = len(data)
    members["manifest.json"] = json.dumps(manifest).encode()
    _rewrite(run_archive, list(members.items()))
    with pytest.raises(ArchiveError, match="unredacted"):
        verify_run_archive(run_archive)
    members["stdout.txt"] = b""
    for entry in manifest["files"]:
        entry["sha256"] = hashlib.sha256(members[entry["name"]]).hexdigest()
        entry["size_bytes"] = len(members[entry["name"]])
    manifest["run_id"] = "different-run"
    members["manifest.json"] = json.dumps(manifest).encode()
    _rewrite(run_archive, list(members.items()))
    with pytest.raises(ArchiveError, match="identity"):
        verify_run_archive(run_archive)


def test_nonzip_fails_with_domain_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(ArchiveError):
        verify_run_archive(path)


@pytest.mark.parametrize("run_id", ["CON", "nul.txt", "run.", "LPT9"])
def test_nonportable_run_ids_are_rejected_before_extraction(run_archive: Path, run_id: str) -> None:
    members = dict(_members(run_archive))
    manifest = json.loads(members["manifest.json"])
    manifest["run_id"] = run_id
    members["manifest.json"] = json.dumps(manifest).encode()
    _rewrite(run_archive, list(members.items()))
    with pytest.raises(ArchiveError):
        verify_run_archive(run_archive)
