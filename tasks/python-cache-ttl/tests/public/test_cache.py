import pytest
from cachelib import TTLCache


def test_value_is_available_before_expiration() -> None:
    now = [10.0]
    cache = TTLCache(lambda: now[0])
    cache.set("token", "abc", ttl=5)
    now[0] = 14.99
    assert cache.get("token") == "abc"


def test_expired_value_is_missing() -> None:
    now = [10.0]
    cache = TTLCache(lambda: now[0])
    cache.set("token", "abc", ttl=5)
    now[0] = 15.0
    with pytest.raises(KeyError):
        cache.get("token")


def test_overwrite_replaces_value_and_deadline() -> None:
    now = [1.0]
    cache = TTLCache(lambda: now[0])
    cache.set("key", "old", ttl=1)
    now[0] = 1.5
    cache.set("key", "new", ttl=10)
    now[0] = 4.0
    assert cache.get("key") == "new"


def test_delete_reports_whether_a_value_existed() -> None:
    cache = TTLCache(lambda: 0.0)
    cache.set("key", 1)
    assert cache.delete("key") is True
    assert cache.delete("key") is False
