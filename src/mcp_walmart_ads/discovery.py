"""Spec-driven endpoint discovery over the bundled/cached OpenAPI specs.

Indexes operations by ``operationId`` for the two canonical specs (one per
``ad_type``) and resolves an operation's transitive ``components.schemas``
closure, so an agent can list/inspect endpoints and call them by id without the
full spec. Specs are small and reloaded from disk per call, so a freshly
refreshed spec is picked up immediately.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .specs import AD_TYPE_SPEC, SpecError, load_spec

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
SCHEMA_REF_PREFIX = "#/components/schemas/"
_REF_RE = re.compile(r'"\$ref"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class Operation:
    operation_id: str
    ad_type: str
    method: str
    path: str
    summary: str
    tags: tuple[str, ...]
    raw: dict[str, Any]


def _spec_id_for(ad_type: str) -> str:
    spec_id = AD_TYPE_SPEC.get(ad_type)
    if spec_id is None:
        known = ", ".join(sorted(AD_TYPE_SPEC))
        raise SpecError(f"no spec for ad_type {ad_type!r} (known: {known})")
    return spec_id


def _index(ad_type: str) -> tuple[dict[str, Any], dict[str, Operation]]:
    """Load the spec for ``ad_type`` and build its operationId → Operation index."""
    spec = load_spec(_spec_id_for(ad_type))
    ops: dict[str, Operation] = {}
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, raw in methods.items():
            if method.lower() not in HTTP_METHODS or not isinstance(raw, dict):
                continue
            declared = raw.get("operationId")
            op_id = (
                declared if isinstance(declared, str) and declared else f"{method.upper()} {path}"
            )
            tags = raw.get("tags")
            ops[op_id] = Operation(
                operation_id=op_id,
                ad_type=ad_type,
                method=method.lower(),
                path=path,
                summary=str(raw.get("summary") or ""),
                tags=tuple(tags) if isinstance(tags, list) else (),
                raw=raw,
            )
    return spec, ops


def list_endpoints(
    ad_type: str,
    *,
    query: str | None = None,
    tag: str | None = None,
    method: str | None = None,
) -> list[dict[str, Any]]:
    """Return slim records for operations in ``ad_type``'s spec, with filters.

    ``query`` matches (case-insensitive substring) operationId, path, or
    summary; ``tag`` filters by OpenAPI tag; ``method`` filters by HTTP verb.
    """
    _, ops = _index(ad_type)
    q = query.lower() if query else None
    m = method.lower() if method else None
    out: list[dict[str, Any]] = []
    for op in ops.values():
        if q and not (
            q in op.operation_id.lower() or q in op.path.lower() or q in op.summary.lower()
        ):
            continue
        if tag and tag not in op.tags:
            continue
        if m and m != op.method:
            continue
        out.append(
            {
                "operation_id": op.operation_id,
                "method": op.method.upper(),
                "path": op.path,
                "summary": op.summary,
                "tags": list(op.tags),
            }
        )
    return sorted(out, key=lambda r: (r["path"], r["method"]))


def get_operation(ad_type: str, operation_id: str) -> Operation:
    _, ops = _index(ad_type)
    op = ops.get(operation_id)
    if op is None:
        raise SpecError(
            f"operation {operation_id!r} not found in {ad_type} spec "
            "(use list_endpoints to discover ids)"
        )
    return op


def describe_endpoint(ad_type: str, operation_id: str) -> dict[str, Any]:
    """Return one operation plus its transitive ``components.schemas`` closure."""
    spec, ops = _index(ad_type)
    op = ops.get(operation_id)
    if op is None:
        raise SpecError(
            f"operation {operation_id!r} not found in {ad_type} spec "
            "(use list_endpoints to discover ids)"
        )
    return {
        "ad_type": ad_type,
        "operation_id": op.operation_id,
        "method": op.method.upper(),
        "path": op.path,
        "operation": op.raw,
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
