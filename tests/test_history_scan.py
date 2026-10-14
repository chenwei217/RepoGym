from collections.abc import Callable
from pathlib import Path

import pytest

from repogym.history import HistoryError
from repogym.history.scan import inspect_run, read_json_bytes, scan_runs


def test_scan_is_sorted_and_isolates_corruption(run_factory: Callable[..., Path]) -> None:
    later = run_factory("run-z")
    earlier = run_factory("run-a")
    (earlier.parent / "broken").mkdir()
    (earlier.parent / "ignored.txt").write_text("ignored", encoding="utf-8")
    report = scan_runs(later.parent)
    assert [run.run_id for run in report.runs] == ["run-a", "run-z"]
    assert [(d.entry, d.code) for d in report.diagnostics] == [("broken", "invalid_run")]
    assert str(later.parent) not in report.model_dump_json()


def test_legacy_timestamp_is_unknown(run_factory: Callable[..., Path]) -> None:
    run = run_factory(created_at=None)
    (run / "metadata.json").unlink()
    assert inspect_run(run).created_at is None


@pytest.mark.parametrize(
    "changes",
    [
        {"score": float("nan")},
        {"score": 101},
        {"duration_seconds": -1},
        {"task_id": "../escape"},
        {"run_id": "other"},
        {"created_at": "bad"},
        {"created_at": "2026-01-01T00:00:00"},
        {"task_fingerprint": "private value"},
    ],
)
def test_invalid_summaries_fail_closed(run_factory: Callable[..., Path], changes: dict) -> None:
    if "run_id" in changes:
        run = run_factory()
        path = run / "result.json"
        path.write_text(
            path.read_text(encoding="utf-8").replace("run-a", "other"), encoding="utf-8"
        )
    else:
        run = run_factory(**changes)
    with pytest.raises(HistoryError, match=r"Invalid|match"):
        inspect_run(run)


def test_size_limit_and_missing_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "large.json"
    path.write_bytes(b"{}" * 10)
    monkeypatch.setattr("repogym.history.scan.MAX_JSON_BYTES", 8)
    with pytest.raises(HistoryError, match="size limit"):
        read_json_bytes(path)
    with pytest.raises(HistoryError, match="does not exist"):
        scan_runs(tmp_path / "missing")


def test_linked_entries_are_not_followed(
    run_factory: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = run_factory()
    real_linked = __import__("repogym.history.scan", fromlist=["linked"]).linked
    monkeypatch.setattr("repogym.history.scan.linked", lambda p: p == run or real_linked(p))
    report = scan_runs(run.parent)
    assert not report.runs
    assert report.diagnostics[0].code == "unsafe_entry"
    with pytest.raises(HistoryError, match="non-linked"):
        inspect_run(run)
