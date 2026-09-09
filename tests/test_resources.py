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


def test_read_cached_response_json() -> None:
    cache = ResponseCache()
    cache.put("req-x", [{"id": 1}, {"id": 2}])
    result = read_cached_response("req-x", cache)
    assert result is not None
    assert '"id": 1' in result


def test_read_cached_response_missing() -> None:
    cache = ResponseCache()
    assert read_cached_response("nope", cache) is None


def test_read_cached_response_string_verbatim() -> None:
    """Non-JSON bodies (CSV/TSV reports, gzip-decompressed snapshots) must not
    be JSON-encoded -- the resource is the only way to retrieve them in full."""
    cache = ResponseCache()
    cache.put("req-s", "id,name\n1,widget\n")
    assert read_cached_response("req-s", cache) == "id,name\n1,widget\n"


def test_read_cached_response_non_ascii() -> None:
    cache = ResponseCache()
    cache.put("req-cn", {"name": "京东"})
    result = read_cached_response("req-cn", cache)
    assert result is not None
    assert "京东" in result  # ensure_ascii=False keeps CJK readable
