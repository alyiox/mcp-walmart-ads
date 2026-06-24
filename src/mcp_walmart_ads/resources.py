from __future__ import annotations

import json
import time
from typing import Any


class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    def put(self, request_id: str, data: Any) -> None:
        self._store[request_id] = (data, time.monotonic())

    def get(self, request_id: str) -> Any | None:
        entry = self._store.get(request_id)
        if entry is None:
            return None
        data, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[request_id]
            return None
        return data

    def list_ids(self) -> list[str]:
        now = time.monotonic()
        expired = [k for k, (_, ts) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        return list(self._store.keys())


def read_cached_response(request_id: str, cache: ResponseCache) -> str | None:
    data = cache.get(request_id)
    if data is None:
        return None
    return json.dumps(data, indent=2)
