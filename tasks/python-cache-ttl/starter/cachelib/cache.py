from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """A minimal in-memory cache using a monotonic clock."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._items: dict[K, tuple[V, float | None]] = {}

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        expires_at = self._clock() + ttl if ttl else None
        self._items[key] = (value, expires_at)

    def get(self, key: K) -> V:
        value, _expires_at = self._items[key]
        return value

    def delete(self, key: K) -> bool:
        return self._items.pop(key, None) is not None
