from pathlib import Path

import pytest
from typer.testing import CliRunner

from repogym.archives import import_run_archive
from repogym.archives.models import ArchiveError
from repogym.cli import app


def test_cli_import_verify_and_reexport(run_archive: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    destination = tmp_path / "imported"
    destination.mkdir()
    assert runner.invoke(app, ["archive", "verify", str(run_archive)]).exit_code == 0
    imported = runner.invoke(
        app, ["archive", "import", str(run_archive), "--destination", str(destination)]
    )
    assert imported.exit_code == 0, imported.output
    exported = runner.invoke(
        app, ["archive", "export", str(destination / "run-a"), str(tmp_path / "copy.zip")]
    )
    assert exported.exit_code == 0, exported.output
    assert runner.invoke(app, ["archive", "verify", str(tmp_path / "absent")]).exit_code == 10
    assert (
        runner.invoke(
            app, ["archive", "export", str(tmp_path / "absent"), str(tmp_path / "bad.zip")]
        ).exit_code
        == 10
    )


def test_import_refuses_conflict_missing_destination_and_lock(
    run_archive: Path,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "run-a").mkdir()
    with pytest.raises(ArchiveError, match="already exists"):
        import_run_archive(run_archive, destination)
    assert not list(destination.glob(".import-*"))
    with pytest.raises(ArchiveError, match="non-linked"):
        import_run_archive(run_archive, tmp_path / "missing")
    lock = destination / ".import-run-a.lock"
    lock.write_bytes(b"owned by another importer")
    with pytest.raises(ArchiveError, match="lock"):
        import_run_archive(run_archive, destination)
    assert lock.read_bytes() == b"owned by another importer"


def test_failed_publication_cleans_only_owned_staging(
    run_archive: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()

    def fail(source: Path, target: Path) -> None:
        raise PermissionError("simulated publication failure")

    monkeypatch.setattr("repogym.archives.importer.os.rename", fail)
    with pytest.raises(ArchiveError, match="Could not publish"):
        import_run_archive(run_archive, destination)
    assert list(destination.iterdir()) == []
