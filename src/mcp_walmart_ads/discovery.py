"""Spec-driven endpoint discovery over the bundled/cached OpenAPI specs.

Indexes every operation across all 33 specs and resolves an operation's
transitive ``components.schemas`` closure, so an agent can list/inspect
endpoints and call them by id without the full spec.

An operation is addressed three ways, in decreasing specificity:

* ``api`` + bare ``operationId`` -- the api scopes the lookup.
* a qualified id, ``<api>:<operationId>`` (e.g.
  ``walmart:marketplace:order-management:getAllOrders``). An api id always has
  exactly two colons and an operationId never has one, so the final colon splits
  them unambiguously.
* a bare ``operationId`` alone, which resolves when it is unique across every
  spec. Some ids are not: ``getAnItem``, ``getReturns``, ``getTaxonomyResponse``
  and ``priceBulkUploads`` each appear in several Marketplace specs, and those
  raise an error naming the candidates rather than guessing.

Eight operations declare no ``operationId`` at all and get ``METHOD /path``.

Indexes are cached per spec file and invalidated on mtime change, so a freshly
refreshed spec is picked up without restarting the server.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .platforms import platform_for, platform_of
from .specs import API_IDS, SpecError, load_spec, meta_for, mirrors_of, spec_path

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
SCHEMA_REF_PREFIX = "#/components/schemas/"
_REF_RE = re.compile(r'"\$ref"\s*:\s*"([^"]+)"')

# Headers the server owns end to end. They are injected from config and the
# operation's own declarations, and stripped from ``describe_endpoint`` output so
# an agent never tries to supply a token, a signature, or the one legal
# WM_MARKET value.
MANAGED_HEADERS = frozenset(
    {
        "authorization",
        "accept",
        "content-type",
        "wm_sec.access_token",
        "wm_svc.name",
        "wm_qos.correlation_id",
        "wm_market",
        "wm_sandbox",
        "wm_global_version",
        "wm_consumer.channel.type",
        "wm_consumer.id",
        "wm_consumer.intimestamp",
        "wm_partner.id",
        "wm_partner_id",
        "wm_sec.timestamp",
        "wm_sec.auth_signature",
        "wm_sec.key_version",
    }
)


@dataclass(frozen=True)
class Operation:
    operation_id: str
    api: str
    method: str
    path: str
    summary: str
    tags: tuple[str, ...]
    raw: dict[str, Any]

    @property
    def qualified_id(self) -> str:
        return f"{self.api}:{self.operation_id}"

    @property
    def platform(self) -> str:
        return platform_of(self.api)

    def header_params(self) -> list[dict[str, Any]]:
        return [
            p
            for p in (self.raw.get("parameters") or [])
            if isinstance(p, dict) and p.get("in") == "header"
        ]

    def declares_header(self, name: str) -> bool:
        folded = name.casefold()
        return any(str(p.get("name", "")).casefold() == folded for p in self.header_params())

    def response_media_types(self) -> tuple[str, ...]:
        """Media types the operation declares for its success responses.

        Some endpoints negotiate strictly and answer ``Accept: */*`` with a 406
        listing what they can produce, so a request has to name a concrete type.
        """
        out: list[str] = []
        for code, response in (self.raw.get("responses") or {}).items():
            if not str(code).startswith("2") or not isinstance(response, dict):
                continue
            for media_type in response.get("content") or {}:
                if media_type not in out:
                    out.append(media_type)
        return tuple(out)

    def header_enum(self, name: str) -> str | None:
        """First declared enum value for a header, when the spec constrains it.

        ``WM_MARKET`` is spelled ``US`` in most specs and ``us`` in two; sending
        the operation's own casing avoids arguing with the validator.
        """
        folded = name.casefold()
        for param in self.header_params():
            if str(param.get("name", "")).casefold() != folded:
                continue
            schema = param.get("schema")
            if not isinstance(schema, dict):
                continue
            enum = schema.get("enum")
            if isinstance(enum, list) and enum and isinstance(enum[0], str):
                return enum[0]
        return None


# api -> (mtime, spec, {operation_id: Operation})
_cache: dict[str, tuple[float, dict[str, Any], dict[str, Operation]]] = {}


def _load_cached(api: str) -> tuple[dict[str, Any], dict[str, Operation]]:
    """Load a spec and its operation index, reusing the cache while mtime holds."""
    path = spec_path(api)
    mtime = path.stat().st_mtime

    cached = _cache.get(api)
    if cached is not None and cached[0] == mtime:
        return cached[1], cached[2]

    spec = load_spec(api)
    ops: dict[str, Operation] = {}
    for path_str, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, raw in methods.items():
            if method.lower() not in HTTP_METHODS or not isinstance(raw, dict):
                continue
            declared = raw.get("operationId")
            op_id = (
                declared
                if isinstance(declared, str) and declared
                else f"{method.upper()} {path_str}"
            )
            tags = raw.get("tags")
            ops[op_id] = Operation(
                operation_id=op_id,
                api=api,
                method=method.lower(),
                path=path_str,
                summary=str(raw.get("summary") or ""),
                tags=tuple(tags) if isinstance(tags, list) else (),
                raw=raw,
            )

    _cache[api] = (mtime, spec, ops)
    return spec, ops


def _available_apis(platform: str | None = None) -> list[str]:
    """Api ids that have a spec file on disk, in declaration order."""
    available: list[str] = []
    for api in API_IDS:
        if platform is not None and meta_for(api).platform != platform:
            continue
        try:
            spec_path(api)
        except SpecError:
            continue
        available.append(api)
    return available


def list_apis() -> list[dict[str, Any]]:
    """One row per api: its id, platform, environments, operation count, and title."""
    rows: list[dict[str, Any]] = []
    for api in _available_apis():
        spec, ops = _load_cached(api)
        info = spec.get("info") or {}
        meta = meta_for(api)
        environments = meta.environments_for()
        row: dict[str, Any] = {
            "api": api,
            "platform": meta.platform,
            "title": info.get("title"),
            "version": info.get("version"),
            "operations": len(ops),
            "environments": list(environments) if environments else "from config",
        }
        mirrors = mirrors_of(api)
        if mirrors:
            row["mirrored_by"] = list(mirrors)
        rows.append(row)
    return rows


def list_endpoints(
    *,
    query: str | None = None,
    api: str | None = None,
    platform: str | None = None,
    tag: str | None = None,
    method: str | None = None,
) -> list[dict[str, Any]]:
    """Return slim records for operations across every api, with filters.

    ``query`` matches (case-insensitive substring) operation id, path, or
    summary; ``api`` limits to one spec, ``platform`` to one family; ``tag``
    filters by OpenAPI tag; ``method`` filters by HTTP verb.
    """
    if api is not None:
        meta_for(api)  # raises SpecError on an unknown api
        apis = [api]
    else:
        if platform is not None:
            platform_for(platform)  # raises UnknownPlatform, naming PLATFORM_IDS
        apis = _available_apis(platform)

    q = query.casefold() if query else None
    m = method.casefold() if method else None
    out: list[dict[str, Any]] = []
    for one in apis:
        _, ops = _load_cached(one)
        for op in ops.values():
            if q and not (
                q in op.operation_id.casefold()
                or q in op.path.casefold()
                or q in op.summary.casefold()
            ):
                continue
            if tag and tag not in op.tags:
                continue
            if m and m != op.method:
                continue
            out.append(
                {
                    "operation_id": op.qualified_id,
                    "api": op.api,
                    "method": op.method.upper(),
                    "path": op.path,
                    "summary": op.summary,
                    "tags": list(op.tags),
                }
            )
    return sorted(out, key=lambda r: (r["api"], r["path"], r["method"]))


def get_operation(operation_id: str, *, api: str | None = None) -> Operation:
    """Resolve an operation by bare id within ``api``, qualified id, or unique bare id."""
    if api is not None:
        meta_for(api)
        bare = operation_id
        prefix, _, tail = operation_id.rpartition(":")
        if prefix == api:
            bare = tail
        _, ops = _load_cached(api)
        op = ops.get(bare)
        if op is None:
            raise SpecError(
                f"operation {bare!r} not found in api {api!r} (use list_endpoints to discover ids)"
            )
        return op

    prefix, _, tail = operation_id.rpartition(":")
    if prefix in API_IDS:
        return get_operation(tail, api=prefix)

    matches = [
        op
        for one in _available_apis()
        for op in [_load_cached(one)[1].get(operation_id)]
        if op is not None
    ]
    if not matches:
        raise SpecError(
            f"operation {operation_id!r} not found in any api (use list_endpoints to discover ids)"
        )
    if len(matches) > 1:
        candidates = ", ".join(op.qualified_id for op in matches)
        raise SpecError(
            f"operation id {operation_id!r} is ambiguous — qualify it as one of: {candidates}"
        )
    return matches[0]


def describe_endpoint(operation_id: str, *, api: str | None = None) -> dict[str, Any]:
    """Return one operation plus its transitive ``components.schemas`` closure.

    Deliberately does not report ``mirrored_by``. Mirroring is a property of an
    api pair, not of an operation: Walmart Connect and Sam's Club share only 13
    of their 90 distinct sponsored-products operation ids, so surfacing it here
    would suggest an operation-level equivalence that mostly does not hold.
    :func:`list_apis` reports it, where the claim is exactly true.

    Server-managed headers are removed from the parameter list: they are injected
    from config and the spec itself, so surfacing them would invite an agent to
    supply an access token, a signature, or the single legal ``WM_MARKET`` value.
    """
    op = get_operation(operation_id, api=api)
    spec, _ = _load_cached(op.api)
    meta = meta_for(op.api)
    environments = meta.environments_for()

    raw = dict(op.raw)
    params = raw.get("parameters")
    if isinstance(params, list):
        raw["parameters"] = [
            p
            for p in params
            if not (
                isinstance(p, dict)
                and p.get("in") == "header"
                and str(p.get("name", "")).casefold() in MANAGED_HEADERS
            )
        ]

    return {
        "operation_id": op.qualified_id,
        "api": op.api,
        "platform": op.platform,
        "method": op.method.upper(),
        "path": op.path,
        "environments": list(environments) if environments else "from config",
        "operation": raw,
        "components": {"schemas": _resolve_refs(spec, op.raw)},
    }


def _collect_refs(value: Any) -> list[str]:
    return _REF_RE.findall(json.dumps(value))


def _resolve_refs(spec: dict[str, Any], op_raw: dict[str, Any]) -> dict[str, Any]:
    """Walk every ``#/components/schemas/<name>`` ref reachable from ``op_raw``."""
    components = (spec.get("components") or {}).get("schemas") or {}
    if not isinstance(components, dict):
        return {}
    seen: dict[str, Any] = {}
    queue = _collect_refs(op_raw)
    while queue:
        ref = queue.pop()
        if not ref.startswith(SCHEMA_REF_PREFIX):
            continue
        name = ref[len(SCHEMA_REF_PREFIX) :]
        if name in seen:
            continue
        schema = components.get(name)
        if schema is None:
            continue
        seen[name] = schema
        queue.extend(_collect_refs(schema))
    return seen
