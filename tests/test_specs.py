from __future__ import annotations

import asyncio
import json
import os
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


# ── sources ───────────────────────────────────────────────────────────────────


def test_registry_source_builds_its_registry_url():
    source = RegistrySource("abc123")
    assert source.url == "https://dash.readme.com/api/v1/api-registry/abc123"


def test_samsclub_is_the_only_url_sourced_spec():
    url_sourced = [m.spec_id for m in SPECS if isinstance(m.source, UrlSource)]
    assert url_sourced == ["samsclub:ads:sponsored-products"]


@pytest.mark.asyncio
async def test_auth_headers_are_attached_only_for_an_authenticated_url_source():
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
            seen[url] = headers
            return httpx.Response(200, json={"openapi": "3.0.0"}, request=httpx.Request("GET", url))

    original = httpx.AsyncClient
    httpx.AsyncClient = FakeClient  # type: ignore[misc, assignment]
    try:
        await specs.fetch_spec(UrlSource("https://example.test/a"), headers={"X-Sig": "1"})
        await specs.fetch_spec(
            UrlSource("https://example.test/b", auth=True), headers={"X-Sig": "1"}
        )
        await specs.fetch_spec(RegistrySource("uuid-1"), headers={"X-Sig": "1"})
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]

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
    """With no bundled copy behind it, an unreadable file is still an error."""
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(specs, "BUNDLE_DIR", tmp_path / "empty")
    target = tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json")
    with pytest.raises(SpecError) as excinfo:
        specs.load_spec("walmart:ads:sponsored-products")
    assert "not valid JSON" in str(excinfo.value)
    assert str(target) in str(excinfo.value)


@pytest.mark.parametrize(
    "body",
    [pytest.param("{not json", id="truncated"), pytest.param('["a"]', id="not an object")],
)
def test_an_unusable_cached_spec_falls_back_to_the_bundle(
    body: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    target = tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"
    target.parent.mkdir(parents=True)
    target.write_text(body)

    spec = specs.load_spec("walmart:ads:sponsored-products")

    assert spec["info"]["title"]
    assert not target.exists(), "the unusable cached copy is discarded, not left to fail again"
    assert specs.spec_path("walmart:ads:sponsored-products") == specs.bundled_path(
        specs.meta_for("walmart:ads:sponsored-products")
    )


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


def _stub_fetch(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    """Answer every fetch from memory: ``result``, or ``result(source)`` if callable."""

    async def fetch(source, headers=None, timeout=30.0, deadline=60.0):
        return result(source) if callable(result) else result

    monkeypatch.setattr(specs, "fetch_spec", fetch)


@pytest.mark.asyncio
async def test_refresh_writes_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(
        monkeypatch,
        {
            "openapi": "3.0.0",
            "info": {"version": "9.9"},
            "paths": {"/a": {"get": {"operationId": "a"}}},
        },
    )
    rows = await specs.refresh("walmart:ads:sponsored-products")
    assert rows == [
        {
            "api": "walmart:ads:sponsored-products",
            "status": "written",
            "version": "9.9",
            "operations": 1,
        }
    ]
    assert (tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json").is_file()


@pytest.mark.asyncio
async def test_refresh_reports_per_spec_errors_without_aborting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)

    def flaky(source):
        if isinstance(source, UrlSource):
            raise httpx.ConnectError("boom")
        return {"openapi": "3.0.0", "info": {}, "paths": {"/a": {"get": {}}}}

    _stub_fetch(monkeypatch, flaky)
    rows = await specs.refresh()
    statuses = {r["api"]: r["status"] for r in rows}
    assert statuses["samsclub:ads:sponsored-products"] == "error"
    assert statuses["walmart:ads:sponsored-products"] == "written"
    assert len(rows) == len(SPECS)


@pytest.mark.asyncio
async def test_refresh_of_an_unknown_api_raises():
    with pytest.raises(SpecError):
        await specs.refresh("walmart:marketplace:nope")


@pytest.mark.parametrize(
    "document",
    [
        pytest.param({"message": "Not Found"}, id="error body served as 200"),
        pytest.param({"openapi": "3.0.0", "paths": {}}, id="no paths"),
        pytest.param({"openapi": "3.0.0", "paths": {"/a": {"summary": "x"}}}, id="no methods"),
        pytest.param([{"openapi": "3.0.0"}], id="not an object"),
    ],
)
@pytest.mark.asyncio
async def test_refresh_refuses_a_document_with_no_operations(
    document: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, document)
    rows = await specs.refresh("walmart:ads:sponsored-products")
    assert rows[0]["status"] == "error"
    assert "no operations" in rows[0]["error"]
    assert list(tmp_path.rglob("*.json")) == []


def test_write_spec_is_atomic_and_compact(tmp_path: Path):
    target = tmp_path / "nested" / "x.json"
    assert specs.write_spec(target, {"a": 1, "b": "é"}) is True
    assert target.read_text(encoding="utf-8") == '{"a":1,"b":"é"}\n'
    assert list(tmp_path.rglob("*.tmp")) == []


def test_write_spec_leaves_an_identical_file_alone(tmp_path: Path):
    target = tmp_path / "x.json"
    specs.write_spec(target, {"a": 1})
    os.utime(target, (0, 0))

    assert specs.write_spec(target, {"a": 1}) is False
    assert target.stat().st_mtime == 0

    assert specs.write_spec(target, {"a": 2}) is True
    assert target.stat().st_mtime != 0


@pytest.mark.asyncio
async def test_refresh_reports_an_unchanged_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, {"info": {"version": "1"}, "paths": {"/a": {"get": {}}}})
    assert (await specs.refresh("walmart:ads:display"))[0]["status"] == "written"
    assert (await specs.refresh("walmart:ads:display"))[0]["status"] == "unchanged"


def test_spec_meta_defaults_are_surface_and_no_suffix():
    meta = SpecMeta("walmart:ads:x", RegistrySource("u"))
    assert meta.in_surface is True
    assert meta.base_suffix == ""
    assert meta.platform == "walmart:ads"
    assert meta.name == "x"
    assert meta.suffix == "ads:x"
    assert meta.rel_path == "walmart/ads/x.openapi.json"


# ── the auxiliary specs are addressable, just not discoverable ────────────────


def test_the_unknown_api_error_lists_every_spec_it_accepts():
    with pytest.raises(SpecError) as excinfo:
        specs.meta_for("walmart:ads:no-such-thing")
    message = str(excinfo.value)
    # Must name the auxiliary ids too: they are valid here, so omitting them
    # would tell a caller they do not exist.
    assert "walmart:ads:ad-id-token" in message
    assert "walmart:ads:conversions" in message
    assert "walmart:marketplace:order-management" in message


# ── background refresh ────────────────────────────────────────────────────────


def _state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "spec-state.json").read_text(encoding="utf-8"))


def _good_doc(_source=None) -> dict:
    return {"info": {"version": "1"}, "paths": {"/a": {"get": {}}}}


@pytest.mark.asyncio
async def test_a_sweep_records_every_spec_it_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, _good_doc())

    rows = await specs.refresh_due(now=1000.0)

    assert len(rows) == len(SPECS)
    recorded = _state(tmp_path)["specs"]
    assert set(recorded) == {m.spec_id for m in SPECS}
    assert all(row["attempted"] == 1000.0 for row in recorded.values())


@pytest.mark.asyncio
async def test_a_spec_refreshed_inside_the_interval_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, _good_doc())

    assert await specs.refresh_due(interval=100.0, now=1000.0) != []
    assert await specs.refresh_due(interval=100.0, now=1050.0) == []
    assert len(await specs.refresh_due(interval=100.0, now=1200.0)) == len(SPECS)


@pytest.mark.asyncio
async def test_force_ignores_the_interval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, _good_doc())

    await specs.refresh_due(interval=100.0, now=1000.0)
    assert len(await specs.refresh_due(interval=100.0, force=True, now=1001.0)) == len(SPECS)


@pytest.mark.asyncio
async def test_a_live_lease_holds_off_a_second_sweeper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Stand in for another process mid-sweep: a lease that has not yet expired.
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, _good_doc())
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "spec-state.json").write_text(json.dumps({"lease_expires": 2000.0}))

    assert await specs.refresh_due(now=1999.0) == []
    assert await specs.refresh_due(now=2001.0) != []


@pytest.mark.asyncio
async def test_a_failed_spec_is_not_retried_until_the_next_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)

    def broken(source):
        raise httpx.ConnectError("upstream down")

    _stub_fetch(monkeypatch, broken)
    rows = await specs.refresh_due(interval=100.0, now=1000.0)

    assert {r["status"] for r in rows} == {"error"}
    assert _state(tmp_path)["specs"]["walmart:ads:display"]["attempted"] == 1000.0
    # An upstream that is down is retried once per interval, not on every tick.
    assert await specs.refresh_due(interval=100.0, now=1050.0) == []


@pytest.mark.asyncio
async def test_an_interrupted_sweep_resumes_where_it_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    seen: list[str] = []

    def fail_after_two(source):
        seen.append(source.url)
        if len(seen) > 2:
            raise RuntimeError("process died")
        return _good_doc()

    _stub_fetch(monkeypatch, fail_after_two)
    with pytest.raises(RuntimeError):
        await specs.refresh_due(now=1000.0)

    done = set(_state(tmp_path)["specs"])
    assert len(done) == 2

    # The lease has lapsed; the next sweeper picks up the rest, not the whole set.
    seen.clear()
    _stub_fetch(monkeypatch, _good_doc())
    rows = await specs.refresh_due(now=1000.0 + specs.LEASE_TTL + 1)
    assert {r["api"] for r in rows} == {m.spec_id for m in SPECS} - done


@pytest.mark.asyncio
async def test_an_unreadable_state_file_is_treated_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A crash can truncate the state mid-write; it is derived data, so a damaged
    # read costs one extra sweep rather than raising.
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    _stub_fetch(monkeypatch, _good_doc())
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "spec-state.json").write_bytes(b'{"lease_expires": 20')

    assert len(await specs.refresh_due(now=1000.0)) == len(SPECS)


@pytest.mark.asyncio
async def test_cancelling_a_sweep_releases_the_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)

    def cancel_on_second(source):
        if (tmp_path / "spec-state.json").is_file() and _state(tmp_path).get("specs"):
            raise asyncio.CancelledError
        return _good_doc()

    _stub_fetch(monkeypatch, cancel_on_second)
    with pytest.raises(asyncio.CancelledError):
        await specs.refresh_due(now=1000.0)

    # Without the release, the next process waits out the whole TTL.
    assert _state(tmp_path)["lease_expires"] == 0.0


@pytest.mark.asyncio
async def test_the_loop_survives_a_failing_sweep(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    async def exploding(**_):
        nonlocal calls
        calls += 1
        raise RuntimeError("network gone")

    monkeypatch.setattr(specs, "refresh_due", exploding)
    task = asyncio.create_task(specs.refresh_loop(0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls > 1  # a failed sweep must not end the loop
