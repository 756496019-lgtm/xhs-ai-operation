"""TTL Store 测试。"""

import time
from ttl_store import TTLStore


def test_set_and_pop():
    store = TTLStore(default_ttl=60)
    store.set("k1", {"data": "val"})
    assert store.pop("k1") == {"data": "val"}


def test_pop_removes_entry():
    store = TTLStore(default_ttl=60)
    store.set("k1", {"data": "val"})
    store.pop("k1")
    assert store.pop("k1") is None


def test_pop_missing_key_returns_none():
    store = TTLStore(default_ttl=60)
    assert store.pop("nonexistent") is None


def test_pop_missing_key_returns_default():
    store = TTLStore(default_ttl=60)
    assert store.pop("nonexistent", "fallback") == "fallback"


def test_len():
    store = TTLStore(default_ttl=60)
    store.set("a", 1)
    store.set("b", 2)
    assert len(store) == 2
    store.pop("a")
    assert len(store) == 1


def test_expiry_cleanup():
    store = TTLStore(default_ttl=60)
    store.set("short", {"x": 1}, ttl=1)
    store.set("long", {"y": 2}, ttl=60)
    time.sleep(1.5)
    removed = store.cleanup_once()
    assert removed == 1
    assert store.pop("short") is None
    assert store.pop("long") == {"y": 2}


def test_overwrite_key():
    store = TTLStore(default_ttl=60)
    store.set("k", "v1")
    store.set("k", "v2")
    assert store.pop("k") == "v2"
