from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from mcp_walmart_ads import specs
from mcp_walmart_ads.specs import (
    API_IDS,
    MAX_EXAMPLE_BYTES,
    SPECS,
    RegistrySource,
    SpecError,
    SpecMeta,
    UrlSource,
    prune_spec,
)

# ── table integrity ───────────────────────────────────────────────────────────


def test_every_declared_spec_has_a_bundled_file():
    missing = [m.spec_id for m in SPECS if not specs.bundled_path(m).is_file()]
    assert missing == []


def test_no_bundled_file_is_undeclared():
    declared = {specs.bundled_path(m).resolve() for m in SPECS}
    on_disk = set(specs.BUNDLE_DIR.rglob("*.openapi.json"))
    assert on_disk - declared == set()


def test_spec_ids_are_unique_and_platform_qualified():
    ids = [m.spec_id for m in SPECS]
    assert len(ids) == len(set(ids))
    assert all(m.spec_id.count(":") == 2 for m in SPECS)
    assert all(m.spec_id.startswith(m.platform + ":") for m in SPECS)


def test_api_surface_excludes_the_auxiliary_connect_specs():
    aux = {m.spec_id for m in SPECS if not m.in_surface}
    assert aux == {"walmart:ads:ad-id-token", "walmart:ads:conversions"}
    assert aux.isdisjoint(API_IDS)


def test_rel_path_derives_from_the_spec_id():
    meta = specs.meta_for("walmart:marketplace:order-management")
    assert meta.rel_path == "walmart/marketplace/order-management.openapi.json"


def test_unknown_api_names_the_known_ones():
    with pytest.raises(SpecError) as excinfo:
        specs.meta_for("walmart:marketplace:no-such-domain")
    assert "walmart:ads:sponsored-products" in str(excinfo.value)


# ── sources ───────────────────────────────────────────────────────────────────


def test_registry_source_builds_its_registry_url():
    source = RegistrySource("abc123")
    assert source.url == "https://dash.readme.com/api/v1/api-registry/abc123"


def test_samsclub_is_the_only_url_sourced_spec():
    url_sourced = [m.spec_id for m in SPECS if isinstance(m.source, UrlSource)]
    assert url_sourced == ["samsclub:ads:sponsored-products"]


def test_url_source_defaults_to_unauthenticated():
    meta = specs.meta_for("samsclub:ads:sponsored-products")
    assert isinstance(meta.source, UrlSource)
    assert meta.source.auth is False


def test_auth_headers_are_attached_only_for_an_authenticated_url_source():
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
            seen[url] = headers
            return httpx.Response(200, json={"openapi": "3.0.0"}, request=httpx.Request("GET", url))

    original = httpx.Client
    httpx.Client = FakeClient  # type: ignore[misc, assignment]
    try:
        specs.fetch_spec(UrlSource("https://example.test/a"), headers={"X-Sig": "1"})
        specs.fetch_spec(UrlSource("https://example.test/b", auth=True), headers={"X-Sig": "1"})
        specs.fetch_spec(RegistrySource("uuid-1"), headers={"X-Sig": "1"})
    finally:
        httpx.Client = original  # type: ignore[misc]

    assert seen["https://example.test/a"] is None
    assert seen["https://example.test/b"] == {"X-Sig": "1"}
    assert seen["https://dash.readme.com/api/v1/api-registry/uuid-1"] is None


# ── environments and base URLs ────────────────────────────────────────────────


def test_marketplace_specs_inherit_the_platform_environments():
    assert specs.meta_for("walmart:marketplace:order-management").environments_for() == (
        "production",
        "sandbox",
    )


def test_ads_specs_defer_their_environments_to_the_config():
    assert specs.meta_for("walmart:ads:sponsored-products").environments_for() is None
    assert specs.meta_for("samsclub:ads:sponsored-products").environments_for() is None


def test_single_environment_specs_are_gated():
    assert specs.meta_for("walmart:marketplace:recommendations-api").environments_for() == (
        "production",
    )
    assert specs.meta_for("walmart:marketplace:simulations-api").environments_for() == ("sandbox",)


def test_unreachable_environment_raises_naming_what_is_reachable():
    with pytest.raises(SpecError) as excinfo:
        specs.resolve_base_url("walmart:marketplace:simulations-api", "production")
    assert "available: sandbox" in str(excinfo.value)


def test_fixed_base_url_appends_the_declared_suffix():
    assert (
        specs.resolve_base_url("walmart:marketplace:simulations-api", "sandbox")
        == "https://sandbox.walmartapis.com/v1"
    )
    assert (
        specs.resolve_base_url("walmart:marketplace:order-management", "production")
        == "https://marketplace.walmartapis.com"
    )


def test_config_sourced_base_url_is_read_from_the_mapping():
    resolved = specs.resolve_base_url(
        "walmart:ads:sponsored-products",
        "production",
        config_base_urls={"walmart:ads:sponsored-products": "https://advertising.walmart.com/"},
    )
    assert resolved == "https://advertising.walmart.com"


def test_config_sourced_base_url_missing_is_an_error():
    with pytest.raises(SpecError) as excinfo:
        specs.resolve_base_url("walmart:ads:sponsored-products", "production", config_base_urls={})
    assert "no base_url configured" in str(excinfo.value)


# ── loading and pruning ───────────────────────────────────────────────────────


def test_bundled_spec_loads_as_an_openapi_document():
    spec = specs.load_spec("walmart:ads:sponsored-products")
    assert "paths" in spec
    assert spec.get("openapi") or spec.get("swagger")


def test_missing_spec_file_raises():
    with pytest.raises(SpecError):
        specs.spec_path("connect:nonexistent")


def test_malformed_spec_file_names_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    target = tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json")
    with pytest.raises(SpecError) as excinfo:
        specs.load_spec("walmart:ads:sponsored-products")
    assert "not valid JSON" in str(excinfo.value)


def test_cache_takes_precedence_over_the_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    target = tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"openapi": "3.0.0", "paths": {}, "info": {"title": "cached"}}))
    assert specs.load_spec("walmart:ads:sponsored-products")["info"]["title"] == "cached"


def test_prune_keeps_small_examples_and_drops_large_ones():
    node = {"small": {"example": "abc"}, "large": {"example": "x" * (MAX_EXAMPLE_BYTES + 1)}}
    pruned = prune_spec(node)
    assert pruned["small"] == {"example": "abc"}
    assert pruned["large"] == {}


def test_prune_drops_x_readme():
    assert prune_spec({"x-readme": {"proxy-enabled": True}, "keep": 1}) == {"keep": 1}


def test_prune_keeps_a_schema_field_literally_named_example():
    node = {"properties": {"example": {"type": "string"}, "other": {"type": "int"}}}
    assert prune_spec(node) == node


def test_prune_treats_a_field_named_properties_as_a_schema():
    # A field *called* "properties" has a schema of its own, not a name map, so
    # an oversized example inside it must still be dropped.
    node = {
        "properties": {
            "properties": {"type": "object", "example": {"blob": "y" * (MAX_EXAMPLE_BYTES + 1)}}
        }
    }
    assert prune_spec(node) == {"properties": {"properties": {"type": "object"}}}


def test_prune_recurses_through_lists():
    node = {"anyOf": [{"example": "s"}, {"example": "z" * (MAX_EXAMPLE_BYTES + 1)}]}
    assert prune_spec(node) == {"anyOf": [{"example": "s"}, {}]}


def test_bundled_files_are_stored_verbatim():
    # load_spec prunes on the way out; the file itself must keep what upstream
    # served, so a refresh diff shows only real upstream change.
    raw = json.loads(
        specs.bundled_path(specs.meta_for("walmart:marketplace:item-management")).read_text()
    )
    assert raw != specs.load_spec("walmart:marketplace:item-management")


# ── refresh ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_writes_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        specs,
        "fetch_spec",
        lambda source, headers=None, timeout=30.0: {
            "openapi": "3.0.0",
            "info": {"version": "9.9"},
            "paths": {"/a": {}},
        },
    )
    rows = await specs.refresh("walmart:ads:sponsored-products")
    assert rows == [
        {
            "api": "walmart:ads:sponsored-products",
            "status": "written",
            "version": "9.9",
            "paths": 1,
            "cached_at": str(tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"),
        }
    ]
    assert (tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json").is_file()


@pytest.mark.asyncio
async def test_refresh_reports_per_spec_errors_without_aborting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)

    def flaky(source, headers=None, timeout=30.0):
        if isinstance(source, UrlSource):
            raise httpx.ConnectError("boom")
        return {"openapi": "3.0.0", "info": {}, "paths": {}}

    monkeypatch.setattr(specs, "fetch_spec", flaky)
    rows = await specs.refresh()
    statuses = {r["api"]: r["status"] for r in rows}
    assert statuses["samsclub:ads:sponsored-products"] == "error"
    assert statuses["walmart:ads:sponsored-products"] == "written"
    assert len(rows) == len(SPECS)


@pytest.mark.asyncio
async def test_refresh_of_an_unknown_api_raises():
    with pytest.raises(SpecError):
        await specs.refresh("walmart:marketplace:nope")


def test_write_spec_is_atomic_and_compact(tmp_path: Path):
    target = tmp_path / "nested" / "x.json"
    specs.write_spec(target, {"a": 1, "b": "é"})
    assert target.read_text(encoding="utf-8") == '{"a":1,"b":"é"}\n'
    assert list(tmp_path.rglob("*.tmp")) == []


def test_spec_meta_defaults_are_surface_and_no_suffix():
    meta = SpecMeta("walmart:ads:x", RegistrySource("u"))
    assert meta.in_surface is True
    assert meta.base_suffix == ""
    assert meta.platform == "walmart:ads"
    assert meta.name == "x"
    assert meta.suffix == "ads:x"
    assert meta.rel_path == "walmart/ads/x.openapi.json"


# ── mirroring ─────────────────────────────────────────────────────────────────


def test_the_two_sponsored_products_apis_mirror_each_other():
    assert specs.mirrors_of("walmart:ads:sponsored-products") == (
        "samsclub:ads:sponsored-products",
    )
    assert specs.mirrors_of("samsclub:ads:sponsored-products") == (
        "walmart:ads:sponsored-products",
    )


def test_an_api_with_no_counterpart_mirrors_nothing():
    assert specs.mirrors_of("walmart:ads:display") == ()
    assert specs.mirrors_of("walmart:marketplace:order-management") == ()


def test_mirroring_is_keyed_on_the_line_and_name_suffix():
    left = specs.meta_for("walmart:ads:sponsored-products")
    right = specs.meta_for("samsclub:ads:sponsored-products")
    assert left.suffix == right.suffix == "ads:sponsored-products"
    assert left.platform != right.platform


def test_mirrors_never_include_an_auxiliary_spec():
    for meta in SPECS:
        assert all(specs.meta_for(m).in_surface for m in specs.mirrors_of(meta.spec_id))


# ── the auxiliary specs are addressable, just not discoverable ────────────────


def test_meta_for_accepts_an_auxiliary_spec():
    # They are callable by raw method+path and refreshable, so meta_for must
    # resolve them even though discovery never lists them.
    for aux in ("walmart:ads:ad-id-token", "walmart:ads:conversions"):
        assert specs.meta_for(aux).in_surface is False


def test_the_unknown_api_error_lists_every_spec_it_accepts():
    with pytest.raises(SpecError) as excinfo:
        specs.meta_for("walmart:ads:no-such-thing")
    message = str(excinfo.value)
    # Must name the auxiliary ids too: they are valid here, so omitting them
    # would tell a caller they do not exist.
    assert "walmart:ads:ad-id-token" in message
    assert "walmart:ads:conversions" in message
    assert "walmart:marketplace:order-management" in message
