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


def read_cached_response(request_id: str, cache: ResponseCache) -> str | None:
    """Return the cached body as text, or ``None`` if missing/expired.

    JSON bodies are re-serialized with indentation; string bodies (non-JSON
    responses, and gzip-decompressed report downloads) are returned verbatim --
    JSON-encoding them would hand back a quoted blob with escaped newlines
    instead of the file.
    """
    data = cache.get(request_id)
    if data is None:
        return None
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2, ensure_ascii=False)
