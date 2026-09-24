import pytest
from cachelib import TTLCache


def test_zero_ttl_is_never_observable() -> None:
    cache = TTLCache(lambda: 100.0)
    cache.set("flash", "value", ttl=0)
    with pytest.raises(KeyError):
        cache.get("flash")


def test_missing_key_raises_key_error() -> None:
    cache = TTLCache(lambda: 0.0)
    with pytest.raises(KeyError):
        cache.get("unknown")


def test_none_ttl_does_not_expire() -> None:
    now = [0.0]
    cache = TTLCache(lambda: now[0])
    cache.set("stable", 42)
    now[0] = 1_000_000.0
    assert cache.get("stable") == 42


def test_delete_removes_unexpired_entry() -> None:
    cache = TTLCache(lambda: 0.0)
    cache.set("key", "value", ttl=10)
    cache.delete("key")
    with pytest.raises(KeyError):
        cache.get("key")
