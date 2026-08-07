"""Disk cache: keying, expiry, and corruption behaviour."""
from __future__ import annotations

import datetime as dt

from edgeloop.data.cache import DiskCache

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def test_key_is_stable_and_param_order_independent():
    a = DiskCache.build_key("quote", {"symbol": "NVDA", "limit": 5}, "2026-08-07")
    b = DiskCache.build_key("quote", {"limit": 5, "symbol": "NVDA"}, "2026-08-07")
    assert a == b


def test_key_varies_with_date():
    """Keying on the date gives EOD data a free daily rollover."""
    a = DiskCache.build_key("quote", {"symbol": "NVDA"}, "2026-08-07")
    b = DiskCache.build_key("quote", {"symbol": "NVDA"}, "2026-08-06")
    assert a != b


def test_key_varies_with_params_and_endpoint():
    base = DiskCache.build_key("quote", {"symbol": "NVDA"}, "2026-08-07")
    assert base != DiskCache.build_key("quote", {"symbol": "AMD"}, "2026-08-07")
    assert base != DiskCache.build_key("profile", {"symbol": "NVDA"}, "2026-08-07")


def test_round_trip(tmp_path):
    cache = DiskCache(tmp_path)
    key = DiskCache.build_key("quote", {"symbol": "NVDA"}, "2026-08-07")
    cache.put(key, "quote", {"symbol": "NVDA"}, [{"price": 223.96}], 3600, NOW)
    entry = cache.get(key)
    assert entry is not None
    assert entry.body == [{"price": 223.96}]
    assert entry.stored_at == NOW


def test_miss_returns_none(tmp_path):
    assert DiskCache(tmp_path).get("nope") is None


def test_expiry_is_ttl_relative(tmp_path):
    cache = DiskCache(tmp_path)
    key = "k"
    entry = cache.put(key, "quote", {}, [], ttl_seconds=900, now=NOW)
    assert not entry.expired(NOW + dt.timedelta(seconds=899))
    assert entry.expired(NOW + dt.timedelta(seconds=901))


def test_corrupt_entry_reads_as_a_miss(tmp_path):
    """Unlike the governor, a corrupt cache entry can only cost a refetch,
    and refetching is the safe direction."""
    cache = DiskCache(tmp_path)
    key = "quote/2026-08-07/abc"
    path = cache._path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert cache.get(key) is None


def test_entry_missing_required_field_reads_as_a_miss(tmp_path):
    cache = DiskCache(tmp_path)
    key = "quote/2026-08-07/abc"
    path = cache._path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"endpoint": "quote"}')
    assert cache.get(key) is None


def test_write_is_atomic_leaving_no_temp_files(tmp_path):
    cache = DiskCache(tmp_path)
    cache.put("k", "quote", {}, [1, 2, 3], 60, NOW)
    assert list(tmp_path.rglob("*.tmp")) == []


def test_stats_and_purge(tmp_path):
    cache = DiskCache(tmp_path)
    cache.put(DiskCache.build_key("quote", {"s": "A"}, "2026-08-07"), "quote", {}, [], 60, NOW)
    cache.put(DiskCache.build_key("profile", {"s": "A"}, "2026-08-07"), "profile", {}, [], 60, NOW)
    assert cache.stats()["entries"] == 2
    assert cache.purge("quote") == 1
    assert cache.stats()["entries"] == 1


def test_purge_requires_an_explicit_call(tmp_path):
    """Nothing evicts on its own; yesterday's body stays as a record."""
    cache = DiskCache(tmp_path)
    key = "k"
    cache.put(key, "quote", {}, [1], ttl_seconds=0, now=NOW)
    assert cache.get(key) is not None  # expired, but still present
