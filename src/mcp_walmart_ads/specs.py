"""OpenAPI spec bundling, pruning, caching, and runtime refresh.

Every api this server exposes is backed by one bundled OpenAPI document. A
spec's id doubles as its public ``api`` id -- ``<retailer>:<line>:<name>``, e.g.
``walmart:ads:sponsored-products`` -- and determines where it sits on disk
(``specs/<retailer>/<line>/<name>.openapi.json``), so there is one identifier
rather than a table mapping three of them together. Credentials attach at the
two-segment prefix; see :mod:`.platforms`.

Two apis cover the same product surface when their ``<line>:<name>`` suffix
matches -- ``walmart:ads:sponsored-products`` and
``samsclub:ads:sponsored-products`` are one surface behind different
credentials, which is why so many of their operation ids collide. The id says
so on its own, and the overlap is partial (13 shared operation ids of 90), so
nothing reports it as data; the api listing's description states the
convention.

Specs reach us two ways, which is what :data:`SpecSource` distinguishes:

* :class:`RegistrySource` -- Walmart publishes no OpenAPI files, but each ReadMe
  reference page hydrates its HTML with the registry UUIDs of its documents, and
  ``https://dash.readme.com/api/v1/api-registry/<uuid>`` serves the full spec
  without authentication. This covers Walmart Connect and all of Marketplace.
  The opaque UUID is unavoidable: that same HTML advertises readable
  ``/branches/1.0/apis/<name>.json`` URLs, but they are client-side routes --
  fetching two different ones returns the identical 2.4 MB page shell, not a
  spec.
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
import logging
import os
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from filelock import lock_descriptor, unlock_descriptor

from .platforms import platform_for, platform_of

logger = logging.getLogger(__name__)

BUNDLE_DIR = Path(__file__).parent / "specs"
REGISTRY_URL = "https://dash.readme.com/api/v1/api-registry/{uuid}"

# The OpenAPI path-item keys that denote an operation; everything else under a
# path ("parameters", "summary", vendor extensions) is not one.
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

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

# One document's fetch, end to end. An httpx timeout is per socket operation, so
# a slow-drip response never trips it; this is the bound that actually holds.
FETCH_DEADLINE = 60.0

# How long a sweeper's claim on the cache stays valid. It must outlast one
# document's fetch, and it is renewed after each one, so a long sweep never
# expires its own lease. A process that dies mid-sweep blocks the next one for
# at most this long.
LEASE_TTL = 300.0

# How often to sweep when the config does not say. Days is the unit the config
# speaks, because nobody reads 604800 as a week; seconds is what the loop needs.
# Specs move on a release cadence, not an hourly one.
DEFAULT_REFRESH_DAYS = 7.0
DEFAULT_REFRESH_INTERVAL = DEFAULT_REFRESH_DAYS * 86400.0

# Documentation-only OpenAPI keywords, size-limited on load.
_PRUNED_KEYWORDS = frozenset({"example", "examples"})

# Vendor extensions carrying docs-rendering metadata rather than API detail.
_DROPPED_KEYWORDS = frozenset({"x-readme"})

# Largest serialized example payload kept. At 1 KB this keeps the great majority
# of payloads while dropping the multi-megabyte taxonomy blobs that would
# otherwise land in an agent's context verbatim.
MAX_EXAMPLE_BYTES = 1024


def iter_operations(spec: Any) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(path, method, operation)`` for every HTTP operation in a document.

    One definition of what counts as an operation, applied both on the way in --
    :func:`refresh` rejects a fetched document that yields none -- and on the way
    out, where :mod:`.discovery` builds its index from it. Tolerant of any shape,
    because the way in is an untrusted HTTP response, not yet known to be a spec.
    """
    if not isinstance(spec, Mapping):
        return
    paths = spec.get("paths")
    if not isinstance(paths, Mapping):
        return
    for path, methods in paths.items():
        if not isinstance(methods, Mapping):
            continue
        for method, operation in methods.items():
            if method.lower() in HTTP_METHODS and isinstance(operation, dict):
                yield str(path), method.lower(), operation


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


def bundled_path(meta: SpecMeta) -> Path:
    return BUNDLE_DIR / meta.rel_path


def cache_path(meta: SpecMeta) -> Path:
    return cache_dir() / meta.rel_path


def spec_path(spec_id: str) -> Path:
    """Resolve the file a spec loads from, cache taking precedence.

    Existence only -- whether the contents load is :func:`load_spec`'s question,
    and a cached file it rejects is gone by the time this is asked again.
    """
    meta = meta_for(spec_id)
    for path in (cache_path(meta), bundled_path(meta)):
        if path.is_file():
            return path
    raise SpecError(f"no spec file found for {spec_id!r}")


def load_spec(spec_id: str) -> dict[str, Any]:
    """Load a spec, preferring the cached (refreshed) copy over the bundle.

    A cached copy that will not load falls through to the bundled one and is
    deleted. The cache is derived data and the bundle is the floor, so a damaged
    file is worth far less than the api it would otherwise take out: it left the
    api listed -- :func:`spec_path` asks only whether a file exists -- while
    every read of it raised, recoverable only by clearing the cache by hand.
    Deleting is what makes that self-correcting; the next refresh rewrites it.

    Raises only when nothing loads, which means the bundled copy is damaged too.
    """
    meta = meta_for(spec_id)
    problems: list[str] = []
    for path in (cache_path(meta), bundled_path(meta)):
        if not path.is_file():
            continue
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{path} is not valid JSON: {e}")
        else:
            if isinstance(spec, dict):
                return prune_spec(spec)
            problems.append(f"{path} is not a JSON object")
        if path != bundled_path(meta):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # best effort: a cache we cannot delete still falls back
    if problems:
        raise SpecError(f"spec {spec_id!r} could not be loaded: {'; '.join(problems)}")
    raise SpecError(f"no spec file found for {spec_id!r}")


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


async def fetch_spec(
    source: SpecSource,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    deadline: float = FETCH_DEADLINE,
) -> dict[str, Any]:
    """Download a spec from its source.

    Unauthenticated GET by default. A :class:`UrlSource` with ``auth`` set
    attaches the caller's signed ``WM_*``/Bearer ``headers``.

    ``timeout`` bounds each socket operation and ``deadline`` bounds the whole
    fetch. Both are needed: a response delivered one slow byte at a time resets
    the per-operation clock forever and would otherwise hang a sweep with no
    bound at all. Async rather than threaded because a deadline over a worker
    thread stops the waiting, not the request -- the thread would keep running.
    """
    needs_auth = isinstance(source, UrlSource) and source.auth
    request_headers = headers if (needs_auth and headers) else None
    async with asyncio.timeout(deadline):
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(source.url, headers=request_headers)
            response.raise_for_status()
            return response.json()


def write_spec(target: Path, spec: dict[str, Any]) -> bool:
    """Atomically write a spec verbatim, returning whether anything changed.

    Stored unpruned -- the file is the source of truth, and :func:`load_spec`
    applies the reduction. Serialized compactly because these files are machine
    input, and indenting 33 documents costs more bytes than any stripping saves.

    A byte-identical document is not rewritten. The comparison is exact rather
    than hashed because the bytes are right there, and it earns its keep beyond
    the saved write: :mod:`.discovery` keys its index on mtime, so rewriting an
    unchanged file makes every running server re-parse that spec for nothing.

    The scratch file is unique per writer. A name derived only from the target
    is shared by every process writing that document, and two interleaved
    writers produce a file that is complete, corrupt, and installed atomically
    -- worse than a partial one, because nothing downstream can detect it.
    """
    body = (json.dumps(spec, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    if target.is_file() and target.read_bytes() == body:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)  # leave litter, never a trap
        raise
    return True


async def _refresh_one(
    meta: SpecMeta,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch, validate, and install one spec, reporting the outcome as a row.

    The single write path. Both the explicit :func:`refresh` and the background
    :func:`refresh_due` drive this, so the trust boundary below cannot be true
    of one and not the other.

    A fetched document is installed only once it yields an operation. The cache
    outranks the bundle, so an upstream that answers ``200`` with something that
    is not a spec -- an error body, a login page rendered as JSON -- would
    otherwise degrade an api with no way back short of deleting the cache by
    hand. Counting operations tests the property that matters, which is whether
    the server still works after the write.
    """
    try:
        spec = await fetch_spec(meta.source, headers=headers)
        operations = sum(1 for _ in iter_operations(spec))
        if operations == 0:
            raise SpecError("fetched document declares no operations")
        written = await asyncio.to_thread(write_spec, cache_path(meta), spec)
    except (
        httpx.HTTPError,
        json.JSONDecodeError,
        OSError,
        SpecError,
        TimeoutError,
        ValueError,
    ) as e:
        return {"api": meta.spec_id, "status": "error", "error": str(e)}
    info = spec.get("info") or {}
    return {
        "api": meta.spec_id,
        "status": "written" if written else "unchanged",
        "version": info.get("version"),
        "operations": operations,
    }


async def refresh(
    spec_id: str | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Re-fetch one spec (by id) or all, writing each to the user cache.

    Per-spec errors are reported in the result row rather than aborting the
    batch. Returns one row per spec with ``status`` ``written``, ``unchanged``,
    or ``error``.

    A fetched document is written only once it yields an operation. The cache
    outranks the bundle, so an upstream that answers ``200`` with something that
    is not a spec -- an error body, a login page rendered as JSON -- would
    otherwise degrade an api with no way back short of deleting the cache by
    hand. Counting operations tests the property that matters, which is whether
    the server still works after the write.
    """
    metas = [meta_for(spec_id)] if spec_id is not None else list(SPECS)
    async with _refresh_lock:
        return [await _refresh_one(meta, headers=headers) for meta in metas]


# ── refresh state ──────────────────────────────────────────────────────────────
#
# One file under the cache root is both the lock and the record. ``lock_descriptor``
# locks a descriptor we opened ourselves and, unlike ``FileLock``, never opens,
# truncates or unlinks the path -- ``FileLock``'s winner truncates the file it
# locks, which would erase the state on every acquire.
#
# The state is rewritten in place rather than replaced. ``os.replace`` would swap
# the inode out from under a held lock, splitting waiters across two inodes and
# breaking the mutual exclusion the lock exists for. A crash mid-write can
# therefore truncate it -- acceptable only because this file is derived data: it
# reads back as empty and costs one extra sweep, while the specs themselves keep
# their atomic install.


def state_path() -> Path:
    """The lease and per-spec refresh record, at the cache root."""
    return cache_dir() / "spec-state.json"


def _read_state(fd: int) -> dict[str, Any]:
    """Parse the open state file, treating anything unusable as empty."""
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(fd, 65536):
        chunks.append(chunk)
    try:
        state = json.loads(b"".join(chunks))
    except (UnicodeDecodeError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _write_state(fd: int, state: dict[str, Any]) -> None:
    body = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, body)
    os.fsync(fd)


@contextmanager
def _locked_state() -> Iterator[tuple[int, dict[str, Any]]]:
    """Hold the state file locked, yielding its descriptor and current contents.

    Blocking, and deliberately short: the caller reads, decides, and writes, with
    no network call inside. Where the filesystem cannot lock at all the sweep
    still runs -- the cost is a duplicated download and a last-writer-wins
    install of identical bytes, which is what the write path is built to absorb.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        try:
            lock_descriptor(fd)
            locked = True
        except OSError as e:
            logger.debug("refresh state lock unavailable (%s); continuing unlocked", e)
        yield fd, _read_state(fd)
    finally:
        if locked:
            with suppress(OSError):
                unlock_descriptor(fd)
        os.close(fd)


def _spec_rows(state: dict[str, Any]) -> dict[str, Any]:
    rows = state.get("specs")
    return rows if isinstance(rows, dict) else {}


def _attempted(state: dict[str, Any], spec_id: str) -> float | None:
    """When this spec was last tried, or ``None`` if it never has been."""
    row = _spec_rows(state).get(spec_id)
    if isinstance(row, dict) and isinstance(row.get("attempted"), int | float):
        return float(row["attempted"])
    return None


def _due(state: dict[str, Any], interval: float, now: float) -> list[SpecMeta]:
    """Specs never attempted, or attempted longer ago than ``interval``.

    Never-attempted is due outright rather than by arithmetic on a zero
    timestamp: the two are different states, and conflating them makes the sweep
    depend on how far the clock happens to sit from the epoch.
    """
    due = []
    for meta in SPECS:
        last = _attempted(state, meta.spec_id)
        if last is None or now - last >= interval:
            due.append(meta)
    return due


def _claim(interval: float, *, force: bool, now: float) -> list[SpecMeta]:
    """Take the lease and return what to sweep, or nothing if another holds it."""
    with _locked_state() as (fd, state):
        if float(state.get("lease_expires") or 0.0) > now:
            return []
        due = list(SPECS) if force else _due(state, interval, now)
        if not due:
            return []
        state["lease_expires"] = now + LEASE_TTL
        _write_state(fd, state)
        return due


def _record(row: dict[str, Any], *, now: float, renew: bool) -> None:
    """Write one spec's outcome and renew (or drop) the lease."""
    with _locked_state() as (fd, state):
        rows = _spec_rows(state)
        entry: dict[str, Any] = {"attempted": now, "status": row["status"]}
        for key in ("version", "operations", "error"):
            if row.get(key) is not None:
                entry[key] = row[key]
        rows[row["api"]] = entry
        state["specs"] = rows
        state["lease_expires"] = (now + LEASE_TTL) if renew else 0.0
        _write_state(fd, state)


def _release() -> None:
    with _locked_state() as (fd, state):
        state["lease_expires"] = 0.0
        _write_state(fd, state)


async def refresh_due(
    *,
    interval: float = DEFAULT_REFRESH_INTERVAL,
    force: bool = False,
    headers: dict[str, str] | None = None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Sweep the specs whose last attempt is older than ``interval``.

    Returns the same rows as :func:`refresh`, one per spec actually swept, and an
    empty list when nothing is due or another process holds the lease.

    The lease is what keeps one sweeper at a time across processes -- the server
    runs one per client session, so without it every session would re-download
    the same 33 documents. It is taken and renewed under the lock, and every
    fetch happens outside it: a caller must never wait on someone else's
    download.

    An attempt is recorded whether it succeeded or failed, so an upstream that is
    down is retried at the next interval rather than on every tick.
    """
    started = time.time() if now is None else now
    async with _refresh_lock:
        due = await asyncio.to_thread(_claim, interval, force=force, now=started)
        if not due:
            return []
        rows: list[dict[str, Any]] = []
        try:
            for index, meta in enumerate(due):
                row = await _refresh_one(meta, headers=headers)
                rows.append(row)
                await asyncio.to_thread(
                    _record,
                    row,
                    now=time.time() if now is None else now,
                    renew=index < len(due) - 1,
                )
        except asyncio.CancelledError:
            # Drop the lease rather than make the next process wait out its TTL.
            with suppress(OSError):
                await asyncio.to_thread(_release)
            raise
        return rows


async def refresh_loop(
    interval: float = DEFAULT_REFRESH_INTERVAL,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    """Sweep at startup, then every ``interval`` seconds, until cancelled.

    Never lets a refresh failure reach the server: a background task that dies on
    a bad network is worse than one that logs and waits for the next tick.
    """
    while True:
        try:
            rows = await refresh_due(interval=interval, headers=headers)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- a sweep must never take the server down
            logger.exception("spec refresh sweep failed")
        else:
            if rows:
                errors = [r for r in rows if r["status"] == "error"]
                logger.info(
                    "refreshed %d spec(s): %d written, %d unchanged, %d error",
                    len(rows),
                    sum(1 for r in rows if r["status"] == "written"),
                    sum(1 for r in rows if r["status"] == "unchanged"),
                    len(errors),
                )
                for row in errors:
                    logger.warning("spec %s: %s", row["api"], row["error"])
        await asyncio.sleep(interval)
