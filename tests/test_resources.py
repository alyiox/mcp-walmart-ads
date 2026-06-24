from __future__ import annotations

import time

from mcp_walmart_ads.resources import (
    ResponseCache,
    read_cached_response,
)


def test_cache_store_and_get() -> None:
    cache = ResponseCache(ttl_seconds=60)
    cache.put("req-1", {"key": "value"})
    assert cache.get("req-1") == {"key": "value"}


def test_cache_expiry() -> None:
    cache = ResponseCache(ttl_seconds=0)
    cache.put("req-1", {"key": "value"})
    time.sleep(0.01)
    assert cache.get("req-1") is None


def test_cache_missing_key() -> None:
    cache = ResponseCache()
    assert cache.get("nonexistent") is None


def test_cache_list_ids() -> None:
    cache = ResponseCache(ttl_seconds=60)
    cache.put("a", 1)
    cache.put("b", 2)
    ids = cache.list_ids()
    assert "a" in ids
    assert "b" in ids


def test_read_cached_response_json() -> None:
    cache = ResponseCache()
    cache.put("req-x", [{"id": 1}, {"id": 2}])
    result = read_cached_response("req-x", cache)
    assert result is not None
    assert '"id": 1' in result


def test_read_cached_response_missing() -> None:
    cache = ResponseCache()
    assert read_cached_response("nope", cache) is None
