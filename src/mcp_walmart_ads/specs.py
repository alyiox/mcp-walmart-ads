"""OpenAPI spec bundling, caching, and runtime refresh.

The Walmart Advertising OpenAPI specs are not publicly published, but each
ReadMe reference page hydrates its HTML with the registry UUIDs of its OpenAPI
documents, and ``https://dash.readme.com/api/v1/api-registry/<uuid>`` serves the
full spec without authentication. The canonical specs are bundled in the package
(``specs/<ad_type>/<name>.openapi.json``) so the server works offline; the
``refresh_specs`` tool re-pulls the latest from the registry into a
user-scoped cache dir, which then takes precedence over the bundle.

Load precedence: user cache dir → bundled package copy.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

BUNDLE_DIR = Path(__file__).parent / "specs"
REGISTRY_URL = "https://dash.readme.com/api/v1/api-registry/{uuid}"


class SpecError(Exception):
    """Raised when a spec is missing, unfetchable, or malformed."""


@dataclass(frozen=True)
class SpecMeta:
    """One bundled OpenAPI spec and its ReadMe api-registry UUID.

    ``ad_type`` is ``search`` or ``display`` for the two canonical specs that
    back the discovery + execution surface; ``None`` for auxiliary Walmart
    services (token generation, conversions) that are bundled and refreshable
    but not part of the ad_type-keyed API surface.
    """

    spec_id: str
    uuid: str
    ad_type: str | None

    @property
    def rel_path(self) -> str:
        return f"{self.spec_id}.openapi.json"


SPECS: tuple[SpecMeta, ...] = (
    SpecMeta("search/sponsored-products", "19bso1c5mqa9d5h0", "search"),
    SpecMeta("display/display-rest-api", "1dgni53lmq8rnndr", "display"),
    SpecMeta("display/ad-id-token-generation", "e1ttaq42mcbiy2r7", None),
    SpecMeta("display/conversion-rest-api", "7ve8omcuu9fg4", None),
)

# ad_type → canonical spec_id (discovery + execution surface).
AD_TYPE_SPEC: dict[str, str] = {m.ad_type: m.spec_id for m in SPECS if m.ad_type}

_refresh_lock = asyncio.Lock()


def cache_dir() -> Path:
    """User-scoped cache root for refreshed specs."""
    return Path.home() / ".cache" / "mcp-walmart-ads" / "specs"


def meta_for(spec_id: str) -> SpecMeta:
    for meta in SPECS:
        if meta.spec_id == spec_id:
            return meta
    known = ", ".join(m.spec_id for m in SPECS)
    raise SpecError(f"unknown spec_id {spec_id!r} (known: {known})")


def bundled_path(meta: SpecMeta) -> Path:
    return BUNDLE_DIR / meta.rel_path


def cache_path(meta: SpecMeta) -> Path:
    return cache_dir() / meta.rel_path


def load_spec(spec_id: str) -> dict[str, Any]:
    """Load a spec, preferring the cached (refreshed) copy over the bundle."""
    meta = meta_for(spec_id)
    for path in (cache_path(meta), bundled_path(meta)):
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SpecError(f"spec {spec_id!r} at {path} is not valid JSON: {e}") from e
    raise SpecError(f"no spec file found for {spec_id!r}")


def fetch_spec(uuid: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Download a spec from the ReadMe api-registry (unauthenticated GET).

    Synchronous so the network call can run off the event loop via
    ``asyncio.to_thread``.
    """
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(REGISTRY_URL.format(uuid=uuid))
        response.raise_for_status()
        return response.json()


def _write_cache(target: Path, spec: dict[str, Any]) -> None:
    """Atomically write a spec to the cache (reader never sees a partial file)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)


async def refresh(spec_id: str | None = None) -> list[dict[str, Any]]:
    """Re-fetch one spec (by id) or all, writing each to the user cache.

    Per-spec errors are reported in the result row rather than aborting the
    batch. Returns one row per spec with ``status`` ``written``/``error``.
    """
    metas = [meta_for(spec_id)] if spec_id is not None else list(SPECS)
    results: list[dict[str, Any]] = []
    async with _refresh_lock:
        for meta in metas:
            try:
                spec = await asyncio.to_thread(fetch_spec, meta.uuid)
                await asyncio.to_thread(_write_cache, cache_path(meta), spec)
            except (httpx.HTTPError, json.JSONDecodeError, OSError) as e:
                results.append({"spec_id": meta.spec_id, "status": "error", "error": str(e)})
                continue
            info = spec.get("info") or {}
            results.append(
                {
                    "spec_id": meta.spec_id,
                    "ad_type": meta.ad_type,
                    "status": "written",
                    "version": info.get("version"),
                    "paths": len(spec.get("paths") or {}),
                    "cached_at": str(cache_path(meta)),
                }
            )
    return results
