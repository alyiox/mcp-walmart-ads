from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from mcp_walmart_ads import discovery, specs
from mcp_walmart_ads.specs import SpecError

# Path counts lock the bundled specs (see OPENAPI extraction).
_EXPECTED_PATHS = {
    "search/sponsored-products": 43,
    "display/display-rest-api": 78,
    "display/ad-id-token-generation": 5,
    "display/conversion-rest-api": 3,
}


def test_manifest_matches_bundled_files() -> None:
    bundled = {
        str(p.relative_to(specs.BUNDLE_DIR)).replace("\\", "/").removesuffix(".openapi.json")
        for p in specs.BUNDLE_DIR.rglob("*.openapi.json")
    }
    manifest = {m.spec_id for m in specs.SPECS}
    assert manifest == bundled


@pytest.mark.parametrize("spec_id,count", _EXPECTED_PATHS.items())
def test_load_bundled_spec(spec_id: str, count: int) -> None:
    spec = specs.load_spec(spec_id)
    assert spec["openapi"].startswith("3.")
    assert len(spec["paths"]) == count


def test_load_unknown_spec_raises() -> None:
    with pytest.raises(SpecError):
        specs.load_spec("search/does-not-exist")


def test_cache_overrides_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    meta = specs.meta_for("search/sponsored-products")
    sentinel = {"openapi": "3.0.1", "paths": {"/sentinel": {}}}
    specs._write_cache(specs.cache_path(meta), sentinel)
    assert specs.load_spec("search/sponsored-products") == sentinel


@pytest.mark.asyncio
async def test_refresh_writes_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    fake = {"openapi": "3.0.1", "info": {"version": "9.9"}, "paths": {"/x": {}}}
    monkeypatch.setattr(specs, "fetch_spec", lambda uuid, **kw: fake)

    rows = await specs.refresh("search/sponsored-products")
    assert len(rows) == 1
    assert rows[0]["status"] == "written"
    assert rows[0]["version"] == "9.9"
    written = json.loads((tmp_path / "search" / "sponsored-products.openapi.json").read_text())
    assert written == fake


@pytest.mark.asyncio
async def test_refresh_reports_per_spec_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)

    def boom(uuid: str, **kw: object) -> dict:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(specs, "fetch_spec", boom)
    rows = await specs.refresh()
    assert len(rows) == len(specs.SPECS)
    assert all(r["status"] == "error" for r in rows)


# ── discovery ────────────────────────────────────────────────────────────────


def test_list_endpoints_search() -> None:
    result = discovery.list_endpoints("search")
    assert len(result) == 69
    assert all({"operation_id", "method", "path"} <= r.keys() for r in result)


def test_list_endpoints_filters() -> None:
    by_method = discovery.list_endpoints("display", method="get")
    assert by_method and all(r["method"] == "GET" for r in by_method)
    by_query = discovery.list_endpoints("search", query="adgroup")
    assert by_query and all(
        "adgroup" in r["operation_id"].lower() or "adgroup" in r["path"].lower() for r in by_query
    )


def test_describe_endpoint_resolves_refs() -> None:
    ops = discovery.list_endpoints("search")
    op_id = next(r["operation_id"] for r in ops if r["method"] == "POST")
    desc = discovery.describe_endpoint("search", op_id)
    assert desc["operation_id"] == op_id
    assert "schemas" in desc["components"]


def test_describe_unknown_operation_raises() -> None:
    with pytest.raises(SpecError):
        discovery.describe_endpoint("search", "NoSuchOperation")


def test_get_operation_unknown_ad_type_raises() -> None:
    with pytest.raises(SpecError):
        discovery.get_operation("video", "whatever")
