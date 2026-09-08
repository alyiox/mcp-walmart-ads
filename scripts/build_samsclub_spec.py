#!/usr/bin/env python
"""Scrape the developer.samsclub.com MkDocs docs into a *candidate* OpenAPI spec.

This runs OFFLINE (in CI or by hand), never at server runtime. It produces a
best-effort candidate spec from the HTML reference pages. The candidate is
committed and diffed on a schedule; CI opens a PR with any change (see
.github/workflows/spec-drift.yml). That PR is the human review gate: a reviewer
ports real changes into the hand-authored canonical spec
(specs/samsclub/sponsored.openapi.json) — the canonical spec is never
overwritten automatically, so hand corrections are protected.

The candidate is intentionally flat (no $ref, no inferred enums/int formats); it
exists to surface doc drift (added/removed/renamed endpoints, params, and body
fields), not to replace the curated spec.

Usage:
    python scripts/build_spec.py                # write the candidate file
    python scripts/build_spec.py --check         # exit 1 if it would change
    python scripts/build_spec.py --out PATH      # write elsewhere (default below)
    python scripts/build_spec.py --base URL      # override docs base for testing

Requires the `spec-build` dependency group:
    uv run --group spec-build python scripts/build_spec.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

DOC_BASE = "https://developer.samsclub.com/API"
# Kept OUTSIDE the package (src/) on purpose: the candidate must not be bundled
# into the wheel or loaded at runtime — it exists only for doc-drift review.
DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent
    / "spec-candidate"
    / "sponsored-ads.candidate.openapi.json"
)
USER_AGENT = "mcp-samsclub-ads spec-builder (+https://github.com/alyiox/mcp-samsclub-ads)"

# Pages that are guides/FAQ, not endpoint references. Everything else in the nav
# is probed; a page with no "End Point:" marker is skipped anyway.
_SKIP_SLUGS = frozenset(
    {
        "overview",
        "authentication",
        "api-partner-based-onboarding",
        "self-serve-onboarding",
        "onboarding-faq",
        "ntb-guide",
        "sba-api-workflow-guide",
        "sv-workflow-guide",
        "wcp-migration-guide",
        "status-code",
    }
)

_TYPE_MAP = {
    "integer": ("integer", None),
    "int": ("integer", None),
    "long": ("integer", "int64"),
    "double": ("number", "double"),
    "float": ("number", "float"),
    "number": ("number", None),
    "decimal": ("number", None),
    "boolean": ("boolean", None),
    "bool": ("boolean", None),
    "date": ("string", "date"),
    "datetime": ("string", "date-time"),
    "string": ("string", None),
    "array": ("array", None),
    "object": ("object", None),
}

_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def fetch(url: str, client: httpx.Client) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def discover_slugs(overview_html: str) -> list[str]:
    """Return doc-page slugs linked from the overview nav (relative ../slug/)."""
    slugs: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'href="\.\./([a-z0-9-]+)/"', overview_html):
        slug = m.group(1)
        if slug in seen or slug in _SKIP_SLUGS:
            continue
        seen.add(slug)
        slugs.append(slug)
    return sorted(slugs)


def _clean(text: str) -> str:
    # Strip zero-width and collapse whitespace.
    return re.sub(r"\s+", " ", text.replace("​", "").replace(" ", " ")).strip()


def _map_type(raw: str) -> dict[str, Any]:
    key = _clean(raw).lower()
    is_array = key.startswith("array") or key.endswith("[]") or "array of" in key
    base = re.sub(r"\[\]$", "", key).replace("array of", "").replace("array", "").strip()
    base = base.split()[0] if base else "string"
    typ, fmt = _TYPE_MAP.get(base, ("string", None))
    if is_array:
        item: dict[str, Any] = {"type": typ}
        if fmt:
            item["format"] = fmt
        return {"type": "array", "items": item}
    schema: dict[str, Any] = {"type": typ}
    if fmt:
        schema["format"] = fmt
    return schema


def _header_index(headers: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, h in enumerate(headers):
        hl = _clean(h).lower()
        if any(k in hl for k in ("parameter", "field", "name", "attribute")):
            idx.setdefault("name", i)
        elif "type" in hl:
            idx["type"] = i
        elif "required" in hl:
            idx["required"] = i
        elif "description" in hl:
            idx["description"] = i
        elif "possible" in hl or "value" in hl:
            idx["values"] = i
    if "name" not in idx and headers:
        idx["name"] = 0
    return idx


def _parse_table(table: Tag) -> list[dict[str, Any]]:
    header_cells = [c.get_text() for c in table.select("thead th")]
    if not header_cells:
        first = table.find("tr")
        header_cells = [c.get_text() for c in first.find_all(["th", "td"])] if first else []
    idx = _header_index(header_cells)
    rows: list[dict[str, Any]] = []
    for tr in table.select("tbody tr") or table.find_all("tr")[1:]:
        cells = [c.get_text() for c in tr.find_all(["td", "th"])]
        if not cells or idx.get("name", 0) >= len(cells):
            continue
        name = _clean(cells[idx["name"]])
        if not name:
            continue
        field: dict[str, Any] = {"name": name}
        if "type" in idx and idx["type"] < len(cells):
            field["type"] = _clean(cells[idx["type"]])
        if "required" in idx and idx["required"] < len(cells):
            field["required"] = _clean(cells[idx["required"]]).lower() in ("y", "yes", "required")
        if "description" in idx and idx["description"] < len(cells):
            field["description"] = _clean(cells[idx["description"]])
        rows.append(field)
    return rows


def _labeled_tables(section: list[Tag]) -> list[tuple[str, Tag]]:
    """Pair each <table> with the nearest preceding <strong>/<p> label."""
    out: list[tuple[str, Tag]] = []
    label = ""
    for el in section:
        if not isinstance(el, Tag):
            continue
        if el.name == "table":
            out.append((label.lower(), el))
            continue
        strong = el.find("strong") if el.name in ("p", "h4", "h5", "h6") else None
        if strong:
            label = _clean(strong.get_text())
        elif el.name == "table":
            out.append((label.lower(), el))
    return out


def _split_sections(content: Tag) -> list[list[Tag]]:
    """Split content into sections, each starting at an h2/h3 heading."""
    sections: list[list[Tag]] = []
    current: list[Tag] = []
    for el in content.children:
        if not isinstance(el, Tag):
            continue
        if el.name in ("h2", "h3"):
            if current:
                sections.append(current)
            current = [el]
        elif current:
            current.append(el)
    if current:
        sections.append(current)
    return sections


def parse_page(slug: str, page_html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "html.parser")
    content = soup.select_one("article") or soup.select_one(".md-content__inner") or soup.body
    if content is None:
        return []
    h1 = content.find("h1")
    page_title = _clean(h1.get_text()) if isinstance(h1, Tag) else slug
    endpoints: list[dict[str, Any]] = []
    for section in _split_sections(content):
        section_text = " ".join(_clean(el.get_text()) for el in section)
        if "End Point:" not in section_text and "Endpoint:" not in section_text:
            continue
        heading = _clean(section[0].get_text()) if section else ""
        path = _find_labeled_value(section, ("end point", "endpoint"))
        method = _find_method(section)
        if not path or not method:
            continue
        summary = _find_labeled_value(section, ("description",)) or heading
        params: list[dict[str, Any]] = []
        body_fields: list[dict[str, Any]] = []
        response_fields: list[dict[str, Any]] = []
        for label, table in _labeled_tables(section):
            rows = _parse_table(table)
            if "quer" in label or "path param" in label:
                params.extend(rows)
            elif "request" in label or "body" in label:
                body_fields.extend(rows)
            elif "response" in label:
                response_fields.extend(rows)
            elif not params and not body_fields:
                (params if method == "GET" else body_fields).extend(rows)
        endpoints.append(
            {
                "tag": page_title,
                "heading": heading,
                "method": method,
                "path": path,
                "summary": summary,
                "params": params,
                "body_fields": body_fields,
                "response_fields": response_fields,
            }
        )
    return endpoints


def _find_labeled_value(section: list[Tag], labels: tuple[str, ...]) -> str:
    for el in section:
        if not isinstance(el, Tag) or el.name != "p":
            continue
        strong = el.find("strong")
        if not strong:
            continue
        key = _clean(strong.get_text()).rstrip(":").lower()
        if key in labels:
            full = _clean(el.get_text())
            return _clean(full[len(_clean(strong.get_text())) :].lstrip(": "))
    return ""


def _find_method(section: list[Tag]) -> str:
    val = _find_labeled_value(section, ("http method", "method"))
    up = _clean(val).upper()
    for m in _HTTP_METHODS:
        if up == m or up.startswith(m + " ") or up == m + ".":
            return m
    return up if up in _HTTP_METHODS else ""


def _properties(fields: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    props: dict[str, Any] = {}
    required: list[str] = []
    for f in fields:
        name = f["name"]
        schema = _map_type(f.get("type", "string"))
        if f.get("description"):
            schema["description"] = f["description"]
        props[name] = schema
        if f.get("required"):
            required.append(name)
    return props, required


def build_spec(all_endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    tags: dict[str, None] = {}
    for ep in all_endpoints:
        tags[ep["tag"]] = None
        op: dict[str, Any] = {
            "operationId": f"{ep['method']} {ep['path']}",
            "summary": ep["summary"],
            "tags": [ep["tag"]],
        }
        parameters = []
        for p in ep["params"]:
            param: dict[str, Any] = {
                "name": p["name"],
                "in": "query",
                "required": bool(p.get("required")),
                "schema": _map_type(p.get("type", "string")),
            }
            if p.get("description"):
                param["description"] = p["description"]
            parameters.append(param)
        if parameters:
            op["parameters"] = parameters
        if ep["body_fields"]:
            props, required = _properties(ep["body_fields"])
            schema: dict[str, Any] = {"type": "object", "properties": props}
            if required:
                schema["required"] = required
            op["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": schema}},
            }
        response_schema: dict[str, Any] = {"type": "object"}
        if ep["response_fields"]:
            props, _ = _properties(ep["response_fields"])
            response_schema = {"type": "array", "items": {"type": "object", "properties": props}}
        op["responses"] = {
            "200": {
                "description": "Success",
                "content": {"application/json": {"schema": response_schema}},
            }
        }
        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op
    return {
        "openapi": "3.0.1",
        "info": {
            "title": "Sam's Club Sponsored Ads API (candidate)",
            "description": (
                "AUTO-GENERATED candidate spec scraped from developer.samsclub.com. "
                "Do not edit by hand and do not load at runtime. Used only for doc-drift "
                "review; port real changes into specs/samsclub/sponsored.openapi.json."
            ),
            "version": "candidate",
        },
        "servers": [{"url": DOC_BASE}],
        "tags": [{"name": t} for t in sorted(tags)],
        "paths": paths,
    }


def scrape(base: str) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        overview = fetch(f"{base}/overview/", client)
        slugs = discover_slugs(overview)
        all_endpoints: list[dict[str, Any]] = []
        for slug in slugs:
            try:
                page = fetch(f"{base}/{slug}/", client)
            except httpx.HTTPError as e:
                print(f"warn: fetch {slug} failed: {e}", file=sys.stderr)
                continue
            eps = parse_page(slug, page)
            if eps:
                print(f"  {slug}: {len(eps)} endpoint(s)", file=sys.stderr)
                all_endpoints.extend(eps)
    return build_spec(all_endpoints)


def _render(spec: dict[str, Any]) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--base", default=DOC_BASE)
    parser.add_argument("--check", action="store_true", help="exit 1 if the candidate would change")
    args = parser.parse_args(argv)

    spec = scrape(args.base)
    rendered = _render(spec)
    op_count = sum(len(v) for v in spec["paths"].values())
    print(f"scraped {len(spec['paths'])} path(s), {op_count} operation(s)", file=sys.stderr)

    existing = args.out.read_text(encoding="utf-8") if args.out.is_file() else None
    if args.check:
        if existing != rendered:
            print("candidate spec is out of date (docs drifted)", file=sys.stderr)
            return 1
        print("candidate spec is up to date", file=sys.stderr)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
