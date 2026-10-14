import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from repogym.history import HistoryError, RunIndex, RunQuery


def test_filters_pagination_and_stale_removal(run_factory: Callable[..., Path]) -> None:
    first = run_factory("run-a", score=50, created_at="2026-01-02T08:00:00+08:00")
    second = run_factory("run-b", status="error", score=0)
    third = run_factory("run-c", task_id="other-task", created_at=None)
    index = RunIndex(first.parent)
    index.refresh()
    assert [r.run_id for r in index.query()] == ["run-a", "run-b", "run-c"]
    assert [r.run_id for r in index.query(RunQuery(task_id="sample-task", max_score=60))] == [
        "run-a",
        "run-b",
    ]
    assert index.query(RunQuery(status="error"))[0].run_id == second.name
    assert index.query(RunQuery(limit=1, offset=1))[0].run_id == "run-b"
    assert len(index.query(RunQuery(since=datetime(2026, 1, 2, tzinfo=UTC)))) == 1
    assert index.query(RunQuery(task_id="' OR 1=1 --")) == []
    (third / "result.json").unlink()
    index.refresh()
    assert len(index.query()) == 2
    assert index.get("run-a").created_at == datetime(2026, 1, 2, tzinfo=UTC)


def test_show_detects_mutation_and_unknown_id(run_factory: Callable[..., Path]) -> None:
    run = run_factory()
    index = RunIndex(run.parent)
    index.refresh()
    with pytest.raises(HistoryError, match="not found"):
        index.get("../escape")
    path = run / "result.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"score": 100', '"score": 50'), encoding="utf-8"
    )
    with pytest.raises(HistoryError, match="changed"):
        index.get(run.name)


def test_refresh_rolls_back_failed_transaction(run_factory: Callable[..., Path]) -> None:
    run = run_factory()
    index = RunIndex(run.parent)
    index.refresh()
    with sqlite3.connect(index.database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_insert BEFORE INSERT ON runs "
            "BEGIN SELECT RAISE(ABORT, 'fixture'); END"
        )
    with pytest.raises(HistoryError, match="Cannot access"):
        index.refresh()
    assert len(index.query()) == 1


def test_versions_corruption_and_model_validation(run_factory: Callable[..., Path]) -> None:
    run = run_factory()
    index = RunIndex(run.parent)
    index.refresh()
    with sqlite3.connect(index.database) as connection:
        connection.execute("UPDATE runs SET summary='{}'")
    with pytest.raises(HistoryError, match="Corrupt"):
        index.query()
    with pytest.raises(HistoryError, match="Corrupt"):
        index.get("run-a")
    with sqlite3.connect(index.database) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(HistoryError, match="Unsupported"):
        index.query()
    for values in (
        {"min_score": 60, "max_score": 10},
        {"since": datetime(2026, 1, 1)},
        {"limit": 0},
        {"offset": -1},
    ):
        with pytest.raises(ValidationError):
            RunQuery(**values)


def test_query_does_not_create_index_or_root(tmp_path: Path) -> None:
    index = RunIndex(tmp_path / "missing")
    with pytest.raises(HistoryError, match="refresh first"):
        index.query()
    assert not index.runs_root.exists()
