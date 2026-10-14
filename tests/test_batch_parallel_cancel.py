import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

import psutil
import pytest
import yaml

from repogym.batch import load_batch, run_batch
from repogym.cache import ExecutionCache
from repogym.exceptions import ExecutionError
from repogym.executors import CancellationToken


def test_precancelled_batch_never_calls_grader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "batch.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "jobs": [{"id": job, "task": "missing", "submission": job} for job in ("b", "a")],
            }
        ),
        encoding="utf-8",
    )

    def forbidden(*args: object, **kwargs: object) -> Path:
        raise AssertionError("must not launch")

    monkeypatch.setattr("repogym.batch.grade_submission", forbidden)
    token = CancellationToken()
    token.cancel()
    directory = run_batch(path, tmp_path / "batches", max_workers=2, cancellation_token=token)
    batch = load_batch(directory)
    assert batch.exit_code == 20
    assert all(job.run_id is None and job.status == "execution_failed" for job in batch.jobs)
    policy = json.loads((directory / "schedule.json").read_text(encoding="utf-8"))
    assert policy["cancellation_requested"]


def test_cancellation_terminates_real_concurrent_children(
    valid_task: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = valid_task / "task.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["execution"]["test_command"] = 'python -c "import time; time.sleep(30)"'
    raw["execution"]["timeout_seconds"] = 10
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "jobs": [
                    {"id": job, "task": str(valid_task), "submission": job} for job in ("b", "a")
                ],
            }
        ),
        encoding="utf-8",
    )
    original = subprocess.Popen
    started = Event()
    lock = Lock()
    pids: list[int] = []

    def observe(*args: Any, **kwargs: Any) -> Any:
        process = original(*args, **kwargs)
        with lock:
            pids.append(process.pid)
            if len(pids) == 2:
                started.set()
        return process

    monkeypatch.setattr("repogym.executors.local.subprocess.Popen", observe)
    token = CancellationToken()

    def cancel_after_launch() -> None:
        if started.wait(10):
            token.cancel()

    watcher = Thread(target=cancel_after_launch, daemon=True)
    watcher.start()
    try:
        directory = run_batch(
            manifest,
            tmp_path / "batches",
            tmp_path / "runs",
            None,
            max_workers=2,
            cancellation_token=token,
        )
    finally:
        token.cancel()
        watcher.join(timeout=2)
    assert started.is_set() and not watcher.is_alive()
    assert len(pids) == 2
    assert all(not psutil.pid_exists(pid) for pid in pids)
    batch = load_batch(directory)
    assert batch.exit_code == 20
    assert all(job.result is not None and job.result.status == "cancelled" for job in batch.jobs)


def test_cache_wait_cancellation_preserves_the_existing_owner(tmp_path: Path) -> None:
    cache = ExecutionCache(tmp_path / "cache")
    key = "a" * 64
    waiting = Event()

    class ObservedToken(CancellationToken):
        def wait(self, timeout: float) -> bool:
            waiting.set()
            return super().wait(timeout)

    token = ObservedToken()

    def wait_for_lock() -> None:
        with cache.lock(key, timeout_seconds=60, cancellation_token=token):
            raise AssertionError("cancelled waiter must not acquire the lock")

    with cache.lock(key):
        owner = (cache.locks / f"{key}.lock").read_bytes()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(wait_for_lock)
            assert waiting.wait(10)
            token.cancel()
            with pytest.raises(ExecutionError, match="Cancelled"):
                pending.result(timeout=10)
        assert (cache.locks / f"{key}.lock").read_bytes() == owner
    assert not (cache.locks / f"{key}.lock").exists()
    with (
        pytest.raises(ExecutionError, match="Cancelled"),
        cache.lock(key, cancellation_token=token),
    ):
        raise AssertionError("pre-cancelled lock must not be acquired")
