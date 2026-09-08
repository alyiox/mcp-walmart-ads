"""OpenAPI spec bundling, pruning, caching, and runtime refresh.

Every api this server exposes is backed by one bundled OpenAPI document. A
spec's id doubles as its public ``api`` id -- ``<retailer>:<line>:<name>``, e.g.
``walmart:ads:sponsored-products`` -- and determines where it sits on disk
(``specs/<retailer>/<line>/<name>.openapi.json``), so there is one identifier
rather than a table mapping three of them together. Credentials attach at the
two-segment prefix; see :mod:`.platforms`.

Two apis *mirror* each other when their ``<line>:<name>`` suffix matches:
``walmart:ads:sponsored-products`` and ``samsclub:ads:sponsored-products`` are
the same surface behind different credentials, which is why so many of their
operation ids collide. :func:`mirrors_of` reports that so an agent can transfer
what it knows from one to the other.

Specs reach us two ways, which is what :data:`SpecSource` distinguishes:

* :class:`RegistrySource` -- Walmart publishes no OpenAPI files, but each ReadMe
  reference page hydrates its HTML with the registry UUIDs of its documents, and
  ``https://dash.readme.com/api/v1/api-registry/<uuid>`` serves the full spec
  without authentication. This covers Walmart Connect and all of Marketplace.
* :class:`UrlSource` -- Sam's Club publishes neither files nor a registry, so its
  spec is hand-authored from the developer docs and refreshed from the raw URL of
  the committed file. That lets hand corrections ship without a release. ``auth``
  is ``False`` today; once partner credentials exist the URL can point at the
  authenticated live Swagger backend and the fetch will be signed.

Load precedence: user cache dir -> bundled package copy.

Files on disk are stored **verbatim** as the source served them, so nothing is
lost and a refresh diff shows exactly what changed upstream. Stripping happens
on the way out, in :func:`load_spec`, which makes the reduction a runtime policy
retunable without re-downloading 33 documents.

What :func:`prune_spec` removes:

* Oversized inline ``example``/``examples`` payloads. These are wildly skewed --
  the median is 16 bytes, while two ``/v3/items/taxonomy`` payloads alone account
  for 3.25 MB. Small ones are worth keeping, since they show the date, sku, and
  identifier formats an agent would otherwise guess, so the cut is by size.
* ``x-readme`` -- the docs platform's own rendering metadata
  (``samples-languages``, ``proxy-enabled``), which says nothing about the API.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .platforms import platform_for, platform_of

BUNDLE_DIR = Path(__file__).parent / "specs"
REGISTRY_URL = "https://dash.readme.com/api/v1/api-registry/{uuid}"

# Raw URL of the committed Sam's Club spec. Refreshing requires this to resolve
# at runtime; if the repo is private, point it at a public raw-content host or an
# authenticated source (auth=True).
_SAMSCLUB_SOURCE_URL = (
    "https://raw.githubusercontent.com/alyiox/mcp-walmart-ads/main/"
    "src/mcp_walmart_ads/specs/samsclub/ads/sponsored-products.openapi.json"
)


class SpecError(Exception):
    """Raised when a spec is missing, unfetchable, malformed, or unreachable."""


@dataclass(frozen=True)
class RegistrySource:
    """A ReadMe api-registry document, fetched by UUID."""

    uuid: str

    @property
    def url(self) -> str:
        return REGISTRY_URL.format(uuid=self.uuid)


@dataclass(frozen=True)
class UrlSource:
    """A spec fetched from a plain URL, signed when ``auth`` is set."""

    url: str
    auth: bool = False


SpecSource = RegistrySource | UrlSource


@dataclass(frozen=True)
class SpecMeta:
    """One bundled OpenAPI spec, its source, and where it is reachable.

    ``in_surface`` is ``False`` for auxiliary documents that are bundled and
    refreshable but not part of the discovery namespace -- Walmart Connect's
    ad-id token and conversion services, which an agent reaches by raw
    method+path rather than by operation id. They remain valid ``api`` values for
    ``call_endpoint`` and ``refresh_specs``.

    ``environments`` overrides the platform's own set for the two Marketplace
    specs that exist in only one, and ``base_suffix`` is appended to the
    environment base URL for the one spec that declares a versioned host
    (``simulations-api`` at ``https://sandbox.walmartapis.com/v1``).
    """

    spec_id: str
    source: SpecSource
    in_surface: bool = True
    environments: tuple[str, ...] | None = None
    base_suffix: str = ""

    @property
    def platform(self) -> str:
        """The two-segment credential prefix, e.g. ``walmart:ads``."""
        return platform_of(self.spec_id)

    @property
    def name(self) -> str:
        """The final segment, e.g. ``sponsored-products``."""
        return self.spec_id.split(":", 2)[2]

    @property
    def suffix(self) -> str:
        """``<line>:<name>`` -- what mirrored apis share."""
        return self.spec_id.split(":", 1)[1]

    @property
    def rel_path(self) -> str:
        return f"{self.platform.replace(':', '/')}/{self.name}.openapi.json"

    def environments_for(self) -> tuple[str, ...] | None:
        """Environments this spec is reachable in, or ``None`` when config decides."""
        if self.environments is not None:
            return self.environments
        return platform_for(self.platform).environments


SPECS: tuple[SpecMeta, ...] = (
    # -- Walmart Connect Ads -----------------------------------------------------
    SpecMeta("walmart:ads:sponsored-products", RegistrySource("19bso1c5mqa9d5h0")),
    SpecMeta("walmart:ads:display", RegistrySource("1dgni53lmq8rnndr")),
    SpecMeta("walmart:ads:ad-id-token", RegistrySource("e1ttaq42mcbiy2r7"), in_surface=False),
    SpecMeta("walmart:ads:conversions", RegistrySource("7ve8omcuu9fg4"), in_surface=False),
    # -- Sam's Club Sponsored Ads ------------------------------------------------
    SpecMeta("samsclub:ads:sponsored-products", UrlSource(_SAMSCLUB_SOURCE_URL)),
    # -- Walmart Marketplace -----------------------------------------------------
    SpecMeta("walmart:marketplace:advertising", RegistrySource("mr9kmmqzd85v3")),
    SpecMeta("walmart:marketplace:assortment-recommendations", RegistrySource("13foynfmmobukfmi")),
    SpecMeta("walmart:marketplace:authentication", RegistrySource("a9esg267mowj5di6")),
    SpecMeta("walmart:marketplace:claims", RegistrySource("79bqa2jmfedtkpg")),
    SpecMeta("walmart:marketplace:disputes-management", RegistrySource("8p3xm33mj3exh1b")),
    SpecMeta("walmart:marketplace:feed-management", RegistrySource("1ll8566gmsf4pry5")),
    SpecMeta("walmart:marketplace:fulfillment-management", RegistrySource("gqmq6domrobwc0d")),
    SpecMeta("walmart:marketplace:insights-management", RegistrySource("d7xjqfjmsi2tzdi")),
    SpecMeta("walmart:marketplace:inventory-management", RegistrySource("22eckdhmr9igu74")),
    SpecMeta("walmart:marketplace:item-management", RegistrySource("5q259gms7zbtw0")),
    SpecMeta("walmart:marketplace:lag-time", RegistrySource("1zzm8322midmdp55")),
    SpecMeta("walmart:marketplace:notifications-management", RegistrySource("9r21x31mqtwfz9u")),
    SpecMeta("walmart:marketplace:on-request-report-management", RegistrySource("d50o1zmsxhe94g")),
    SpecMeta("walmart:marketplace:order-management", RegistrySource("ckuhkx9bms7x4mtd")),
    SpecMeta("walmart:marketplace:payment-reports", RegistrySource("3meqaxj10mfedzr2w")),
    SpecMeta("walmart:marketplace:payments", RegistrySource("dpghjmo3ci7ay")),
    SpecMeta("walmart:marketplace:price-management", RegistrySource("1dgni510mmq5hnqm2")),
    SpecMeta("walmart:marketplace:promotion-management", RegistrySource("kgplbyk3mo1plit7")),
    SpecMeta(
        "walmart:marketplace:recommendations-api",
        RegistrySource("er71zz33pmr9ig743"),
        environments=("production",),
    ),
    SpecMeta("walmart:marketplace:returns-management", RegistrySource("16fdhuump2rm1l6")),
    SpecMeta("walmart:marketplace:reviews-acceleration", RegistrySource("1dyxmsvmruw59jp")),
    SpecMeta("walmart:marketplace:rich-media", RegistrySource("b85t6gbmshu71jg")),
    SpecMeta("walmart:marketplace:settings-management", RegistrySource("1hmzcklmshvsx6g")),
    SpecMeta("walmart:marketplace:ship-with-walmart", RegistrySource("jdmu1a73zmrjvjw3x")),
    SpecMeta(
        "walmart:marketplace:simplified-shipping-settings", RegistrySource("1ll856cvmsf1yqr4")
    ),
    SpecMeta(
        "walmart:marketplace:simulations-api",
        RegistrySource("1jfaw5ymqbastk5"),
        environments=("sandbox",),
        base_suffix="/v1",
    ),
    SpecMeta("walmart:marketplace:utilities-management", RegistrySource("2pmj1rmfee8qqv")),
    SpecMeta("walmart:marketplace:walmart-plus", RegistrySource("f8nmpc10mhp40c1m")),
)

SPEC_IDS: tuple[str, ...] = tuple(m.spec_id for m in SPECS)

# The ``api`` namespace: spec ids an agent can discover and call by operation id.
API_IDS: tuple[str, ...] = tuple(m.spec_id for m in SPECS if m.in_surface)

_BY_ID: dict[str, SpecMeta] = {m.spec_id: m for m in SPECS}

_refresh_lock = asyncio.Lock()

# Documentation-only OpenAPI keywords, size-limited on load.
_PRUNED_KEYWORDS = frozenset({"example", "examples"})

# Vendor extensions carrying docs-rendering metadata rather than API detail.
_DROPPED_KEYWORDS = frozenset({"x-readme"})

# Largest serialized example payload kept. At 1 KB this keeps the great majority
# of payloads while dropping the multi-megabyte taxonomy blobs that would
# otherwise land in an agent's context verbatim.
MAX_EXAMPLE_BYTES = 1024


def _example_is_small(value: Any) -> bool:
    return len(json.dumps(value, separators=(",", ":"))) <= MAX_EXAMPLE_BYTES


def prune_spec(node: Any, *, in_property_names: bool = False) -> Any:
    """Recursively strip agent-irrelevant weight from a spec document.

    Payloads at or under :data:`MAX_EXAMPLE_BYTES` are kept verbatim; larger ones
    are dropped entirely rather than truncated, since half a JSON document is
    worse than none.

    ``in_property_names`` guards the one place the keywords are not keywords: the
    keys of a ``properties`` map are schema *field names*, so a field
    legitimately called ``example`` must survive. The flag is consumed rather
    than re-derived, because a schema may declare a field *named* ``properties``
    -- ``item-management`` does -- and that field's own schema is a schema, not
    another name map.
    """
    if isinstance(node, list):
        return [prune_spec(item) for item in node]
    if not isinstance(node, dict):
        return node

    if in_property_names:
        return {key: prune_spec(value) for key, value in node.items()}

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED_KEYWORDS:
            continue
        if key in _PRUNED_KEYWORDS:
            if _example_is_small(value):
                out[key] = value
            continue
        out[key] = prune_spec(value, in_property_names=(key == "properties"))
    return out


def cache_dir() -> Path:
    """User-scoped cache root for refreshed specs."""
    return Path.home() / ".cache" / "mcp-walmart-ads" / "specs"


def meta_for(spec_id: str) -> SpecMeta:
    """Look up any bundled spec, auxiliary ones included.

    The error lists all of :data:`SPEC_IDS` rather than :data:`API_IDS`, because
    the two auxiliary specs are accepted here -- they are callable by raw
    method+path and refreshable -- and telling a caller they do not exist would
    be wrong.
    """
    meta = _BY_ID.get(spec_id)
    if meta is None:
        raise SpecError(f"unknown api {spec_id!r} (known: {', '.join(SPEC_IDS)})")
    return meta


def mirrors_of(api: str) -> tuple[str, ...]:
    """Other apis with the same ``<line>:<name>`` suffix, behind other credentials.

    Sam's Club mirrors Walmart Connect's sponsored-products surface, so an agent
    that has learned one can address the other by swapping the retailer.
    """
    meta = meta_for(api)
    return tuple(
        m.spec_id for m in SPECS if m.spec_id != api and m.suffix == meta.suffix and m.in_surface
    )


def bundled_path(meta: SpecMeta) -> Path:
    return BUNDLE_DIR / meta.rel_path


def cache_path(meta: SpecMeta) -> Path:
    return cache_dir() / meta.rel_path


def spec_path(spec_id: str) -> Path:
    """Resolve the file a spec loads from, cache taking precedence."""
    meta = meta_for(spec_id)
    for path in (cache_path(meta), bundled_path(meta)):
        if path.is_file():
            return path
    raise SpecError(f"no spec file found for {spec_id!r}")


def load_spec(spec_id: str) -> dict[str, Any]:
    """Load a spec, preferring the cached (refreshed) copy over the bundle."""
    path = spec_path(spec_id)
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError(f"spec {spec_id!r} at {path} is not valid JSON: {e}") from e
    if not isinstance(spec, dict):
        raise SpecError(f"spec {spec_id!r} at {path} is not a JSON object")
    return prune_spec(spec)


def check_environment(spec_id: str, environment: str) -> SpecMeta:
    """Return the spec's metadata, raising when it is not reachable in ``environment``."""
    meta = meta_for(spec_id)
    reachable = meta.environments_for()
    if reachable is not None and environment not in reachable:
        raise SpecError(
            f"api {spec_id!r} is not available in {environment!r} "
            f"(available: {', '.join(reachable)})"
        )
    return meta


def resolve_base_url(
    spec_id: str,
    environment: str,
    *,
    config_base_urls: Mapping[str, str] | None = None,
) -> str:
    """Resolve the base URL for one api in one environment.

    Marketplace's hosts are fixed in :mod:`.platforms`; the ads platforms read
    one per api from the config, passed in as ``config_base_urls``.
    """
    meta = check_environment(spec_id, environment)
    platform = platform_for(meta.platform)

    if platform.base_urls_from_config:
        base = (config_base_urls or {}).get(spec_id)
        if not base:
            raise SpecError(
                f"no base_url configured for api {spec_id!r} in this region/environment"
            )
        return base.rstrip("/") + meta.base_suffix

    assert platform.base_urls is not None
    base = platform.base_urls.get(environment)
    if base is None:
        raise SpecError(f"platform {platform.id!r} has no base URL for {environment!r}")
    return base + meta.base_suffix


def fetch_spec(
    source: SpecSource,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Download a spec from its source.

    Unauthenticated GET by default. A :class:`UrlSource` with ``auth`` set
    attaches the caller's signed ``WM_*``/Bearer ``headers``. Synchronous so the
    network call can run off the event loop via ``asyncio.to_thread``.
    """
    needs_auth = isinstance(source, UrlSource) and source.auth
    request_headers = headers if (needs_auth and headers) else None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(source.url, headers=request_headers)
        response.raise_for_status()
        return response.json()


def write_spec(target: Path, spec: dict[str, Any]) -> None:
    """Atomically write a spec verbatim (reader never sees a partial file).

    Stored unpruned -- the file is the source of truth, and :func:`load_spec`
    applies the reduction. Serialized compactly because these files are machine
    input, and indenting 33 documents costs more bytes than any stripping saves.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    body = json.dumps(spec, separators=(",", ":"), ensure_ascii=False) + "\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


async def refresh(
    spec_id: str | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Re-fetch one spec (by id) or all, writing each to the user cache.

    Per-spec errors are reported in the result row rather than aborting the
    batch. Returns one row per spec with ``status`` ``written``/``error``.
    """
    metas = [meta_for(spec_id)] if spec_id is not None else list(SPECS)
    results: list[dict[str, Any]] = []
    async with _refresh_lock:
        for meta in metas:
            try:
                spec = await asyncio.to_thread(fetch_spec, meta.source, headers=headers)
                await asyncio.to_thread(write_spec, cache_path(meta), spec)
            except (httpx.HTTPError, json.JSONDecodeError, OSError, ValueError) as e:
                results.append({"api": meta.spec_id, "status": "error", "error": str(e)})
                continue
            info = spec.get("info") or {}
            results.append(
                {
                    "api": meta.spec_id,
                    "status": "written",
                    "version": info.get("version"),
                    "paths": len(spec.get("paths") or {}),
                    "cached_at": str(cache_path(meta)),
                }
            )
    return results
