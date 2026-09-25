from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

import repogym.cache as cache_module
import repogym.cli as cli_module
from repogym.cache import ExecutionCache, build_cache_key
from repogym.cli import app
from repogym.exceptions import CacheError
from repogym.exit_codes import ExitCode
from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.models import ExecutionResult
from repogym.reports import load_run


class PassingExecutor:
    def __init__(self, delay: float = 0) -> None:
        self.calls = 0
        self.delay = delay
        self._lock = threading.Lock()

    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        stdout = ""
        if command[-1] == "tests/public":
            stdout = "1 passed in 0.01s"
        elif "pytest" in command:
            stdout = "2 passed in 0.01s"
        return ExecutionResult(
            command=command,
            return_code=0,
            stdout=stdout,
            stderr="",
            duration_seconds=0.01,
        )


class ErrorExecutor(PassingExecutor):
    def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        with self._lock:
            self.calls += 1
        return ExecutionResult(
            command=command,
            return_code=None,
            stdout="",
            stderr="launch failed",
            duration_seconds=0.01,
        )


def _submission(root: Path) -> Path:
    submission = root / "submission"
    (submission / "src").mkdir(parents=True)
    (submission / "src" / "answer.py").write_text("VALUE = 1\n", encoding="utf-8")
    return submission


def _fake_run(root: Path, run_id: str = "source-run") -> Path:
    run = root / run_id
    run.mkdir(parents=True)
    result = {
        "task_id": "sample-task",
        "run_id": run_id,
        "status": "completed",
        "score": 100,
        "dimensions": {},
        "tests": {"passed": 2, "failed": 0, "total": 2},
        "violations": [],
        "duration_seconds": 0.1,
    }
    (run / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (run / "metadata.json").write_text(
        json.dumps({"schema_version": 1, "created_at": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (run / "stdout.txt").write_text("2 passed\n", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    return run


def test_cache_key_is_stable_and_invalidates_inputs(valid_task: Path, tmp_path: Path) -> None:
    task = load_task(valid_task)
    submission = _submission(tmp_path)

    first = build_cache_key(task, "a" * 64, submission, "executor-a")
    assert first == build_cache_key(task, "a" * 64, submission, "executor-a")
    assert first != build_cache_key(task, "b" * 64, submission, "executor-a")
    assert first != build_cache_key(task, "a" * 64, submission, "executor-b")
    (submission / "src" / "answer.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert first != build_cache_key(task, "a" * 64, submission, "executor-a")

    changed_command = task.model_copy(
        update={
            "execution": task.execution.model_copy(update={"test_command": "python -m pytest -x"})
        }
    )
    assert first != build_cache_key(changed_command, "a" * 64, submission, "executor-a")


def test_cache_key_invalidates_runtime_identity(
    valid_task: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = load_task(valid_task)
    submission = _submission(tmp_path)
    first = build_cache_key(task, "a" * 64, submission, "executor-a")

    monkeypatch.setattr(cache_module.platform, "python_version", lambda: "99.0.0")
    assert first != build_cache_key(task, "a" * 64, submission, "executor-a")


def test_store_inspect_restore_and_clear(tmp_path: Path) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "a" * 64
    cache.store(key, _fake_run(tmp_path / "runs"))

    entries = cache.inspect()
    assert len(entries) == 1 and entries[0].valid and entries[0].size_bytes > 0
    restored = cache.restore(key, tmp_path / "restored", "replay-run")
    assert restored is not None
    result = json.loads((restored / "result.json").read_text(encoding="utf-8"))
    metadata = json.loads((restored / "metadata.json").read_text(encoding="utf-8"))
    assert result["run_id"] == "replay-run"
    assert result["cache"] == {
        "key": key,
        "hit": True,
        "source_run_id": "source-run",
    }
    assert metadata["cache"] == result["cache"]
    assert cache.clear() == 1
    assert cache.inspect() == []


def test_corrupt_entry_is_removed_on_restore(tmp_path: Path) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "b" * 64
    cache.store(key, _fake_run(tmp_path / "runs"))
    entry = cache.entries / key
    (entry / "stdout.txt").write_text("tampered", encoding="utf-8")

    assert not cache.inspect()[0].valid
    assert cache.restore(key, tmp_path / "output", "run") is None
    assert not entry.exists()


def test_failed_publication_leaves_no_visible_partial_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "c" * 64

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("publish interrupted")

    monkeypatch.setattr(cache_module.os, "rename", fail_replace)
    with pytest.raises(CacheError, match="publish interrupted"):
        cache.store(key, _fake_run(tmp_path / "runs"))

    assert not (cache.entries / key).exists()
    assert cache.inspect() == []
    assert not list(cache.entries.glob(".*.tmp"))


def test_publication_retries_transient_windows_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    original = os.rename
    attempts = 0

    def transient(source: Path, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("scanner lock")
        original(source, target)

    monkeypatch.setattr(cache_module, "_WINDOWS", True)
    monkeypatch.setattr(cache_module.os, "rename", transient)
    cache.store("9" * 64, _fake_run(tmp_path / "runs"))

    assert attempts == 3
    assert cache.inspect()[0].valid


def test_lock_serializes_threads_and_recovers_stale_file(tmp_path: Path) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "d" * 64
    active = 0
    maximum = 0
    state_lock = threading.Lock()

    def critical_section() -> None:
        nonlocal active, maximum
        with cache.lock(key):
            with state_lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.05)
            with state_lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _value: critical_section(), range(2)))
    assert maximum == 1

    stale = cache.locks / f"{key}.lock"
    stale.write_text("stale", encoding="utf-8")
    os.utime(stale, (0, 0))
    with cache.lock(key, stale_after_seconds=0):
        assert stale.exists()
    assert not stale.exists()


def test_lock_owner_does_not_remove_successor_lock(tmp_path: Path) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "1" * 64
    path = cache.locks / f"{key}.lock"

    with cache.lock(key):
        path.write_text('{"owner": "successor"}', encoding="ascii")

    assert path.exists()
    path.unlink()


def test_grading_cache_hit_skips_execution_and_materializes_new_run(
    valid_task: Path, tmp_path: Path
) -> None:
    executor = PassingExecutor()
    submission = _submission(tmp_path)
    output = tmp_path / "runs"
    cache = tmp_path / "cache"

    first = grade_submission(valid_task, submission, output, executor, cache_root=cache)
    second = grade_submission(valid_task, submission, output, executor, cache_root=cache)
    first_result, _, _ = load_run(first)
    second_result, _, _ = load_run(second)

    assert first != second
    assert executor.calls == 3
    assert first_result.cache is not None and not first_result.cache.hit
    assert second_result.cache is not None and second_result.cache.hit
    assert second_result.cache.source_run_id == first_result.run_id


def test_concurrent_grades_execute_once(valid_task: Path, tmp_path: Path) -> None:
    executor = PassingExecutor(delay=0.05)
    submission = _submission(tmp_path)
    output = tmp_path / "runs"
    cache = tmp_path / "cache"

    def grade() -> Path:
        return grade_submission(valid_task, submission, output, executor, cache_root=cache)

    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _value: grade(), range(2)))

    assert runs[0] != runs[1]
    assert executor.calls == 3
    results = [load_run(run)[0] for run in runs]
    assert sum(result.cache.hit for result in results if result.cache is not None) == 1


def test_incomplete_grades_are_not_cached(valid_task: Path, tmp_path: Path) -> None:
    executor = ErrorExecutor()
    submission = _submission(tmp_path)
    cache_root = tmp_path / "cache"

    first = grade_submission(
        valid_task, submission, tmp_path / "runs", executor, cache_root=cache_root
    )
    second = grade_submission(
        valid_task, submission, tmp_path / "runs", executor, cache_root=cache_root
    )

    assert load_run(first)[0].status == "error"
    assert load_run(second)[0].status == "error"
    assert executor.calls == 6
    assert ExecutionCache(cache_root).inspect() == []


def test_grading_recovers_corrupt_entry_by_reexecuting(valid_task: Path, tmp_path: Path) -> None:
    executor = PassingExecutor()
    submission = _submission(tmp_path)
    cache_root = tmp_path / "cache"
    grade_submission(valid_task, submission, tmp_path / "runs", executor, cache_root=cache_root)
    cache = ExecutionCache(cache_root)
    entry = cache.entries / cache.inspect()[0].key
    (entry / "stdout.txt").write_text("corrupt", encoding="utf-8")

    recovered = grade_submission(
        valid_task, submission, tmp_path / "runs", executor, cache_root=cache_root
    )

    assert executor.calls == 6
    result = load_run(recovered)[0]
    assert result.cache is not None and not result.cache.hit
    assert cache.inspect()[0].valid


def test_cli_cache_controls_and_disable_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    cache = ExecutionCache(cache_dir)
    cache.store("e" * 64, _fake_run(tmp_path / "runs"))
    runner = CliRunner()

    listed = runner.invoke(app, ["cache", "list", "--cache-dir", str(cache_dir)])
    verified = runner.invoke(app, ["cache", "verify", "--cache-dir", str(cache_dir)])
    cleared = runner.invoke(app, ["cache", "clear", "--cache-dir", str(cache_dir)])
    assert listed.exit_code == ExitCode.SUCCESS and "valid" in listed.stdout
    assert verified.exit_code == ExitCode.SUCCESS and "PASS" in verified.stdout
    assert cleared.exit_code == ExitCode.SUCCESS and "Removed 1" in cleared.stdout

    observed: list[Path | None] = []
    cached_run = _fake_run(tmp_path / "cli-runs", "cli-run")

    def fake_grade(*_args: object, cache_root: Path | None = None, **_kwargs: object) -> Path:
        observed.append(cache_root)
        return cached_run

    monkeypatch.setattr(cli_module, "grade_submission", fake_grade)
    default = runner.invoke(app, ["grade", "task", "--submission", "submission"])
    disabled = runner.invoke(
        app,
        ["grade", "task", "--submission", "submission", "--no-cache"],
    )
    assert default.exit_code == ExitCode.SUCCESS
    assert disabled.exit_code == ExitCode.SUCCESS
    assert observed == [Path(".repogym/cache"), None]


def test_cli_cache_verify_reports_corruption(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache = ExecutionCache(cache_dir)
    key = "f" * 64
    cache.store(key, _fake_run(tmp_path / "runs"))
    (cache.entries / key / "stdout.txt").write_text("tampered", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["cache", "verify", "--cache-dir", str(cache_dir)],
    )

    assert result.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert "FAIL" in result.stderr
    assert (cache.entries / key).exists()
