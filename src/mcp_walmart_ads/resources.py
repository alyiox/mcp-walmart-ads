from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DOCS_DIR = Path(__file__).parent / "docs"


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


def list_doc_resources() -> list[dict[str, str]]:
    """Return all bundled doc resources as {uri, name, description, mime_type}."""
    resources = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        rel = md_file.relative_to(DOCS_DIR)
        parts = rel.with_suffix("").parts
        uri = "wmc://docs/" + "/".join(parts)
        name = " / ".join(p.replace("-", " ").title() for p in parts)
        resources.append(
            {
                "uri": uri,
                "name": f"[WalmartAds] {name} API reference",
                "description": f"[WalmartAds] API reference for {name}. Src: docs.",
                "mime_type": "text/markdown",
            }
        )
    return resources


def read_doc_resource(uri: str) -> str | None:
    """Read a bundled doc resource by URI. Returns markdown content or None."""
    prefix = "wmc://docs/"
    if not uri.startswith(prefix):
        return None
    rel_path = uri[len(prefix) :]
    md_file = (DOCS_DIR / rel_path).with_suffix(".md")
    if not md_file.exists():
        return None
    return md_file.read_text()


def read_cached_response(request_id: str, cache: ResponseCache) -> str | None:
    data = cache.get(request_id)
    if data is None:
        return None
    return json.dumps(data, indent=2)
