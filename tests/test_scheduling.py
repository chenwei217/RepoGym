from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

import pytest

from repogym.executors import CancellationToken
from repogym.scheduling import run_groups


def test_worker_and_pending_future_bounds_with_serial_group_order(monkeypatch) -> None:
    gate = Barrier(2)
    lock = Lock()
    active = peak_active = peak_pending = 0
    futures = []
    order: dict[int, list[int]] = {}

    class ObservedPool(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            nonlocal peak_pending
            future = super().submit(*args, **kwargs)
            with lock:
                futures.append(future)
                peak_pending = max(peak_pending, sum(not item.done() for item in futures))
            return future

    monkeypatch.setattr("repogym.scheduling.ThreadPoolExecutor", ObservedPool)

    def worker(item: tuple[int, int]) -> tuple[int, int]:
        nonlocal active, peak_active
        group, position = item
        with lock:
            active += 1
            peak_active = max(peak_active, active)
            order.setdefault(group, []).append(position)
        gate.wait(timeout=10)
        with lock:
            active -= 1
        return item

    groups = [[(group, position) for position in range(2)] for group in range(4)]
    result = run_groups(groups, worker, max_workers=2, cancellation_token=CancellationToken())
    assert sorted(result) == sorted(item for group in groups for item in group)
    assert peak_active == 2 and peak_pending <= 2
    assert all(positions == [0, 1] for positions in order.values())


def test_serial_empty_and_invalid_worker_counts() -> None:
    token = CancellationToken()
    assert run_groups([[3, 1], [2]], str, max_workers=1, cancellation_token=token) == [
        "3",
        "1",
        "2",
    ]
    assert run_groups([], str, max_workers=2, cancellation_token=token) == []
    for workers in (0, 33, True):
        with pytest.raises(ValueError, match="workers"):
            run_groups([[1]], str, max_workers=workers, cancellation_token=token)


def test_interruption_signals_active_workers_before_pool_shutdown() -> None:
    token = CancellationToken()
    gate = Barrier(2)
    stopped = Event()

    def worker(value: int) -> int:
        gate.wait(timeout=10)
        if value == 0:
            raise KeyboardInterrupt
        assert token.wait(10), "scheduler did not cancel the active peer"
        stopped.set()
        return value

    with pytest.raises(KeyboardInterrupt):
        run_groups([[0], [1]], worker, max_workers=2, cancellation_token=token)
    assert token.cancelled and stopped.is_set()

    def fail(value: int) -> int:
        raise RuntimeError("fixture")

    other = CancellationToken()
    with pytest.raises(RuntimeError):
        run_groups([[1]], fail, max_workers=1, cancellation_token=other)
    assert other.cancelled
