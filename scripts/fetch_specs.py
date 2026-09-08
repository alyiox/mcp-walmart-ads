"""Rebuild the bundled OpenAPI specs from their upstream sources.

Run from the repo root::

    uv run python scripts/fetch_specs.py [api ...]

Writes specs verbatim into ``src/mcp_walmart_ads/specs/<platform>/``. With no
arguments, refreshes every registry-sourced spec. The runtime ``refresh_specs``
tool does the same thing into the user cache dir; this script updates the copy
that ships in the wheel.

Sam's Club is skipped unless named explicitly: its spec is hand-authored from
the developer docs, and its ``UrlSource`` points at the committed file in this
repo, so refetching it would only copy the file onto itself. Use
``scripts/build_samsclub_spec.py`` to regenerate the *candidate* for review
instead.
"""

from __future__ import annotations

import sys

from mcp_walmart_ads.specs import (
    SPECS,
    RegistrySource,
    bundled_path,
    fetch_spec,
    write_spec,
)


def main(argv: list[str]) -> int:
    wanted = set(argv)
    unknown = wanted - {m.spec_id for m in SPECS}
    if unknown:
        print(f"unknown api ids: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    if wanted:
        metas = [m for m in SPECS if m.spec_id in wanted]
    else:
        metas = [m for m in SPECS if isinstance(m.source, RegistrySource)]

    total = 0
    for meta in metas:
        spec = fetch_spec(meta.source)
        target = bundled_path(meta)
        write_spec(target, spec)
        size = target.stat().st_size
        total += size
        paths = len(spec.get("paths") or {})
        print(f"{meta.spec_id:<44}{size / 1024:>8.0f} KB  {paths:>3} paths")

    print(f"\n{len(metas)} specs, {total / 1024 / 1024:.1f} MB bundled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
