"""Bounded group scheduling with cooperative interruption cleanup."""

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TypeVar

from repogym.executors import CancellationToken

T = TypeVar("T")
R = TypeVar("R")
MAX_WORKERS = 32


def run_groups(
    groups: Sequence[Sequence[T]],
    worker: Callable[[T], R],
    *,
    max_workers: int,
    cancellation_token: CancellationToken,
) -> list[R]:
    """Execute each group serially; consumers normalize inter-group completion order.

    A worker must observe the shared token to make interruption cleanup cooperative. Futures are
    bounded by the worker count, even when the manifest contains many independent groups.
    """
    if type(max_workers) is not int or not 1 <= max_workers <= MAX_WORKERS:
        raise ValueError(f"workers must be an integer between 1 and {MAX_WORKERS}")
    if max_workers == 1:
        try:
            return [worker(item) for group in groups for item in group]
        except BaseException:
            cancellation_token.cancel()
            raise

    def execute_group(group: Sequence[T]) -> list[R]:
        return [worker(item) for item in group]

    results: list[R] = []
    iterator = iter(groups)
    pending: set[Future[list[R]]] = set()
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="repogym-batch") as pool:
        try:
            for _ in range(max_workers):
                group = next(iterator, None)
                if group is not None:
                    pending.add(pool.submit(execute_group, group))
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    results.extend(future.result())
                    group = next(iterator, None)
                    if group is not None:
                        pending.add(pool.submit(execute_group, group))
        except BaseException:
            cancellation_token.cancel()
            for future in pending:
                future.cancel()
            raise
    return results
