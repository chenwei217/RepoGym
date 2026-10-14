"""Transactional SQLite inventory derived from run artifacts."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from repogym.history.models import HistoryError, RunQuery, RunSummary, ScanResult
from repogym.history.scan import inspect_run, linked, scan_runs


class RunIndex:
    """A disposable index; refreshing never modifies source run artifacts."""

    def __init__(self, runs_root: Path, database: Path | None = None) -> None:
        self.runs_root = runs_root
        self.database = database or runs_root / ".history.sqlite3"

    @contextmanager
    def _connect(self, create: bool = False) -> Iterator[sqlite3.Connection]:
        if not create and not self.database.exists():
            raise HistoryError("Run index does not exist; run runs refresh first")
        if (self.database.exists() or self.database.is_symlink()) and linked(self.database):
            raise HistoryError("Index may not be a link")
        connection = None
        try:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.database, timeout=10)
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise HistoryError("Unsupported run index schema version")
            if version == 0:
                connection.execute(
                    "CREATE TABLE runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
                    "status TEXT NOT NULL, score REAL NOT NULL, "
                    "created_at TEXT, summary TEXT NOT NULL)"
                )
                connection.execute("CREATE INDEX by_task ON runs(task_id, created_at)")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            yield connection
        except (sqlite3.Error, OSError) as exc:
            raise HistoryError("Cannot access run index; rebuild or choose a new index") from exc
        finally:
            if connection is not None:
                connection.close()

    def refresh(self) -> ScanResult:
        report = scan_runs(self.runs_root)
        with self._connect(create=True) as connection, connection:
            connection.execute("DELETE FROM runs")
            connection.executemany(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        run.run_id,
                        run.task_id,
                        run.status,
                        run.score,
                        run.created_at.isoformat() if run.created_at else None,
                        run.model_dump_json(),
                    )
                    for run in report.runs
                ],
            )
        return report

    def query(self, query: RunQuery | None = None) -> list[RunSummary]:
        selection = query or RunQuery()
        since = selection.since.isoformat() if selection.since else None
        sql = (
            "SELECT summary FROM runs WHERE score >= ? AND score <= ? "
            "AND (? IS NULL OR task_id = ?) AND (? IS NULL OR status = ?) "
            "AND (? IS NULL OR created_at >= ?) "
            "ORDER BY created_at DESC, run_id ASC LIMIT ? OFFSET ?"
        )
        values = (
            selection.min_score,
            selection.max_score,
            selection.task_id,
            selection.task_id,
            selection.status,
            selection.status,
            since,
            since,
            selection.limit,
            selection.offset,
        )
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
        try:
            return [RunSummary.model_validate_json(row[0]) for row in rows]
        except ValueError as exc:
            raise HistoryError("Corrupt indexed summary; refresh the index") from exc

    def get(self, run_id: str) -> RunSummary:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT summary FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise HistoryError("Run not found in index")
        try:
            summary = RunSummary.model_validate_json(row[0])
        except ValueError as exc:
            raise HistoryError("Corrupt indexed summary; refresh the index") from exc
        actual = inspect_run(self.runs_root / summary.run_id)
        if actual.result_sha256 != summary.result_sha256:
            raise HistoryError("Run changed since refresh; refresh the index")
        return actual
