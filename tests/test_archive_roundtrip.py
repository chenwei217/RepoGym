import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from repogym.archives import export_run_archive, import_run_archive, verify_run_archive
from repogym.archives.models import ArchiveError
from repogym.evidence import build_evidence, load_evidence
from repogym.history import RunIndex
from repogym.reports import generate_report, load_run


def test_current_archive_is_deterministic_private_and_replayable(
    run_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = run_factory(candidate_fingerprint="b" * 64)
    marker = "fixture" + "credential42"
    (run / "stdout.txt").write_text(f"api_key={marker} at /home/unit/private.py", encoding="utf-8")
    result, stdout, stderr = load_run(run)
    evidence = build_evidence(result, datetime(2026, 1, 1, tzinfo=UTC), stdout, stderr)
    (run / "evidence.json").write_text(evidence.model_dump_json(), encoding="utf-8")
    (run / "changed_files.json").write_text('["src/answer.py"]', encoding="utf-8")
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    manifest = export_run_archive(run, first)
    export_run_archive(run, second)
    assert first.read_bytes() == second.read_bytes()
    assert verify_run_archive(first) == manifest
    destination = tmp_path / "imported"
    destination.mkdir()
    restored = import_run_archive(first, destination)
    imported, text, _ = load_run(restored)
    assert imported.score == 100
    assert marker not in text and "/home/unit" not in text
    assert marker in (run / "stdout.txt").read_text(encoding="utf-8")
    assert load_evidence(restored).task_id == "sample-task"
    for format_name in ("json", "html", "junit", "sarif"):
        assert generate_report(restored, format_name)
    index = RunIndex(destination)
    index.refresh()
    assert index.get("run-a").score == 100


def test_legacy_archive_without_metadata_or_evidence(
    run_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = run_factory(task_fingerprint=None)
    (run / "metadata.json").unlink()
    archive = tmp_path / "legacy.zip"
    export_run_archive(run, archive)
    destination = tmp_path / "imported"
    destination.mkdir()
    restored = import_run_archive(archive, destination)
    assert load_run(restored)[0].test_evidence.reason == "legacy_run"
    assert {p.name for p in restored.iterdir()} == {"result.json", "stdout.txt", "stderr.txt"}


def test_export_rejects_incomplete_and_existing_targets(
    run_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = run_factory()
    output = tmp_path / "run.zip"
    output.write_bytes(b"existing")
    with pytest.raises(ArchiveError):
        export_run_archive(run, output)
    assert output.read_bytes() == b"existing"
    (run / "stdout.txt").unlink()
    with pytest.raises(ArchiveError):
        export_run_archive(run, tmp_path / "new.zip")
    assert not (tmp_path / "new.zip").exists()
    assert not list(tmp_path.glob(".repogym-archive-*"))


def test_wrong_evidence_association_is_rejected(
    run_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = run_factory()
    result, out, err = load_run(run)
    evidence = build_evidence(result, datetime.now(UTC), out, err)
    raw = evidence.model_dump(mode="json")
    raw["task_id"] = "other-task"
    (run / "evidence.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArchiveError, match="association"):
        export_run_archive(run, tmp_path / "bad.zip")
