from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp_walmart_ads import server
from mcp_walmart_ads.config import load_config
from mcp_walmart_ads.resources import ResponseCache
from tests.conftest import raw_config


@pytest.fixture
def loaded(config_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the server's lazy config at a temp file and reset its memo."""
    cfg = load_config(config_file)
    monkeypatch.setattr(server, "_config", cfg)
    monkeypatch.setattr(server, "_cache", ResponseCache(ttl_seconds=cfg.response_cache_ttl))
    monkeypatch.setattr(server, "tokens", server.TokenManager())
    return cfg


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(server, "_config", None)
    monkeypatch.setattr(server, "_cache", None)
    monkeypatch.setattr(server.config.__globals__["load_config"], "__defaults__", None)
    monkeypatch.setattr(
        server, "load_config", lambda *a, **k: load_config(tmp_path / "absent.json")
    )


def _transport(monkeypatch: pytest.MonkeyPatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    original = httpx.AsyncClient

    async def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return await handler(request)

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return original(*args, transport=httpx.MockTransport(wrapped), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return seen


def _json_ok(payload: Any):
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v3/token"):
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})
        return httpx.Response(200, json=payload)

    return handler


# ── surface ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exactly_five_tools_are_registered():
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == {
        "list_endpoints",
        "describe_endpoint",
        "call_endpoint",
        "download_file",
        "refresh_specs",
    }


@pytest.mark.asyncio
async def test_every_tool_and_resource_description_is_namespaced():
    for tool in await server.mcp.list_tools():
        assert tool.description and tool.description.startswith("[Walmart]")
        for prop in tool.input_schema.get("properties", {}).values():
            assert prop.get("description", "").startswith("[Walmart]")
    for resource in await server.mcp.list_resources():
        assert resource.description and resource.description.startswith("[Walmart]")


@pytest.mark.asyncio
async def test_every_tool_declares_annotations():
    for tool in await server.mcp.list_tools():
        assert tool.annotations is not None


@pytest.mark.asyncio
async def test_discovery_tools_are_read_only_and_closed_world():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    for name in ("list_endpoints", "describe_endpoint"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.open_world_hint is False


@pytest.mark.asyncio
async def test_the_passthrough_tool_takes_the_most_cautious_shape():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    annotations = tools["call_endpoint"].annotations
    assert annotations is not None
    assert annotations.read_only_hint is False
    assert annotations.destructive_hint is True
    assert annotations.idempotent_hint is False
    assert annotations.open_world_hint is True


@pytest.mark.asyncio
async def test_writing_tools_are_idempotent_and_non_destructive():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    for name in ("download_file", "refresh_specs"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is False
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is True


@pytest.mark.asyncio
async def test_the_four_resources_are_registered():
    uris = {str(r.uri) for r in await server.mcp.list_resources()}
    templates = {str(t.uri_template) for t in await server.mcp.list_resource_templates()}
    assert uris == {"wmt://config", "wmt://apis"}
    assert templates == {"wmt://responses/{request_id}", "wmt://curl/{request_id}"}


# ── resources ─────────────────────────────────────────────────────────────────


def test_the_config_resource_never_leaks_credential_material(loaded):
    text = server.get_config()
    for secret in ("secret-1", "connect-bearer", "sams-bearer", "BEGIN PRIVATE KEY"):
        assert secret not in text


def test_the_config_resource_reports_apis_and_advertisers(loaded):
    payload = json.loads(server.get_config())["platforms"]
    assert payload["connect"]["us"]["production"] == {"apis": ["connect:display", "connect:search"]}
    assert payload["marketplace"]["us"]["production"]["advertisers"] == [
        {"id": 7060158, "partner_id": "10001234"},
        {"id": 7060159},
    ]


def test_the_config_resource_surfaces_a_broken_platform_as_an_error(
    write_config, monkeypatch: pytest.MonkeyPatch
):
    data = raw_config()
    data["platforms"]["connect"]["regions"]["us"]["production"].pop("bearer_token")
    cfg = load_config(write_config(data))
    monkeypatch.setattr(server, "_config", cfg)
    monkeypatch.setattr(server, "_cache", ResponseCache())
    payload = json.loads(server.get_config())["platforms"]
    assert "error" in payload["connect"]
    assert "us" in payload["marketplace"]


def test_the_config_resource_reports_a_missing_file_instead_of_raising(unconfigured):
    assert "error" in json.loads(server.get_config())


def test_the_apis_resource_lists_the_whole_namespace():
    apis = json.loads(server.get_apis())["apis"]
    assert len(apis) == 31
    assert {a["platform"] for a in apis} == {"connect", "samsclub", "marketplace"}


def test_the_cached_response_resource_reports_an_unknown_id(loaded):
    assert "No cached response" in server.cached_response_resource("nope")


def test_the_curl_resource_reports_an_unknown_id(loaded):
    assert "No cURL command" in server.cached_curl_resource("nope")


# ── discovery tools ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_endpoints_works_with_no_config_at_all(unconfigured):
    result = await server.list_endpoints(query="orders")
    assert result["count"] > 0


@pytest.mark.asyncio
async def test_describe_endpoint_works_with_no_config_at_all(unconfigured):
    described = await server.describe_endpoint("marketplace:order-management:getAllOrders")
    assert described["method"] == "GET"


@pytest.mark.asyncio
async def test_list_endpoints_reports_an_unknown_api_as_an_error():
    assert "error" in await server.list_endpoints(api="marketplace:nope")


@pytest.mark.asyncio
async def test_list_endpoints_reports_an_unknown_platform_as_an_error():
    assert "error" in await server.list_endpoints(platform="target")


@pytest.mark.asyncio
async def test_describe_endpoint_reports_an_ambiguous_id_as_an_error():
    result = await server.describe_endpoint("AdGroupList")
    assert "ambiguous" in result["error"]


# ── call_endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_operation_id_alone_selects_platform_api_and_route(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _json_ok({"ok": True}))
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="marketplace:order-management:getAllOrders",
        advertiser_id=7060158,
    )
    assert result.status_code == 200
    assert str(seen[-1].url) == "https://marketplace.walmartapis.com/v3/orders"


@pytest.mark.asyncio
async def test_a_signature_platform_operation_routes_to_its_configured_host(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _json_ok({"ok": True}))
    await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="samsclub:sponsored:AdGroupList",
    )
    assert seen[0].url.host == "advertising.samsclub.com"


@pytest.mark.asyncio
async def test_raw_method_and_path_require_an_api(loaded):
    result = await server.call_endpoint(
        region="us", environment="production", method="get", path="/api/v1/unpublished"
    )
    assert "api" in (result.error or "")


@pytest.mark.asyncio
async def test_raw_method_and_path_reach_an_endpoint_absent_from_the_specs(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _json_ok({"ok": True}))
    result = await server.call_endpoint(
        region="us",
        environment="production",
        api="connect:search",
        method="get",
        path="/api/v1/not-in-the-spec",
    )
    assert result.status_code == 200
    assert str(seen[0].url).endswith("/api/v1/not-in-the-spec")


@pytest.mark.asyncio
async def test_an_unknown_api_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="us", environment="production", api="connect:nope", method="get", path="/x"
    )
    assert "unknown api" in (result.error or "")


@pytest.mark.asyncio
async def test_an_unconfigured_region_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="eu", environment="production", operation_id="connect:search:AdGroupList"
    )
    assert "region" in (result.error or "")


@pytest.mark.asyncio
async def test_a_marketplace_call_without_an_advertiser_id_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="marketplace:order-management:getAllOrders",
    )
    assert "advertiser_id" in (result.error or "")


@pytest.mark.asyncio
async def test_a_missing_config_is_reported_as_an_error_not_raised(unconfigured):
    result = await server.call_endpoint(
        region="us", environment="production", operation_id="connect:search:AdGroupList"
    )
    assert "Config file not found" in (result.error or "")


@pytest.mark.asyncio
async def test_a_large_body_is_truncated_and_cached(loaded, monkeypatch: pytest.MonkeyPatch):
    payload = {"rows": [{"i": i, "pad": "x" * 40} for i in range(200)]}
    _transport(monkeypatch, _json_ok(payload))
    result = await server.call_endpoint(
        region="us", environment="production", operation_id="connect:search:AdGroupList"
    )
    assert result.truncated is True
    assert result.cached_at is not None
    request_id = result.cached_at.removeprefix("wmt://responses/")
    assert json.loads(server.cached_response_resource(request_id)) == payload


@pytest.mark.asyncio
async def test_a_small_body_is_returned_whole_with_a_curl_reference(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _json_ok({"ok": True}))
    result = await server.call_endpoint(
        region="us", environment="production", operation_id="connect:search:AdGroupList"
    )
    assert result.body == {"ok": True}
    assert result.truncated is None
    assert result.curl is not None
    curl = server.cached_curl_resource(result.curl.removeprefix("wmt://curl/"))
    assert "connect-bearer" not in curl
    assert "$WM_BEARER_TOKEN" in curl


@pytest.mark.asyncio
async def test_none_valued_result_fields_are_omitted_from_the_payload(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _json_ok({"ok": True}))
    result = await server.call_endpoint(
        region="us", environment="production", operation_id="connect:search:AdGroupList"
    )
    assert "error" not in result.model_dump()
    assert "truncated" not in result.model_dump()


# ── download_file ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_download_with_dest_path_writes_the_bytes(
    loaded, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"col_a,col_b\n1,2\n")

    _transport(monkeypatch, handler)
    target = tmp_path / "out" / "report.csv"
    result = await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/report/1",
        dest_path=str(target),
    )
    assert result.bytes_written == 16
    assert target.read_bytes() == b"col_a,col_b\n1,2\n"


@pytest.mark.asyncio
async def test_a_download_without_dest_path_gunzips_into_the_cache(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=gzip.compress(b"a,b\n1,2\n"))

    _transport(monkeypatch, handler)
    result = await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/snapshot/1",
        advertiser_id=99,
    )
    assert result.cached_at is not None
    request_id = result.cached_at.removeprefix("wmt://responses/")
    assert server.cached_response_resource(request_id) == "a,b\n1,2\n"


@pytest.mark.asyncio
async def test_an_uncompressed_payload_is_cached_verbatim(loaded, monkeypatch: pytest.MonkeyPatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"plain,text\n")

    _transport(monkeypatch, handler)
    result = await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/r",
    )
    assert result.cached_at is not None
    assert (
        server.cached_response_resource(result.cached_at.removeprefix("wmt://responses/"))
        == "plain,text\n"
    )


@pytest.mark.asyncio
async def test_a_binary_payload_without_dest_path_asks_for_one(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xfe\x00\x01binary")

    _transport(monkeypatch, handler)
    result = await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/label.pdf",
    )
    assert "dest_path" in (result.error or "")


@pytest.mark.asyncio
async def test_a_snapshot_download_sends_the_advertiser_as_a_query_parameter(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok")

    seen = _transport(monkeypatch, handler)
    await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/snapshot/1",
        advertiser_id=4242,
    )
    assert dict(seen[0].url.params) == {"advertiserId": "4242"}
    assert seen[0].headers["X-Advertiser-ID"] == "4242"


@pytest.mark.asyncio
async def test_a_bare_url_download_requires_a_platform(loaded):
    result = await server.download_file(
        region="us", environment="production", url="https://x.test/a"
    )
    assert "platform" in (result.error or "")


@pytest.mark.asyncio
async def test_an_operation_id_download_infers_the_platform(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v3/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 900})
        return httpx.Response(200, content=b"report")

    seen = _transport(monkeypatch, handler)
    result = await server.download_file(
        region="us",
        environment="production",
        operation_id="marketplace:on-request-report-management:downloadReport",
        advertiser_id=7060158,
    )
    assert result.error is None, result.error
    assert any(r.url.host == "marketplace.walmartapis.com" for r in seen)


@pytest.mark.asyncio
async def test_a_download_needs_a_url_an_operation_or_a_path(loaded):
    result = await server.download_file(region="us", environment="production", platform="connect")
    assert "provide url" in (result.error or "")


@pytest.mark.asyncio
async def test_a_failed_download_reports_the_status_and_the_hops(
    loaded, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"missing")

    _transport(monkeypatch, handler)
    result = await server.download_file(
        region="us",
        environment="production",
        platform="connect",
        url="https://advertising.walmart.com/gone",
    )
    assert result.status_code == 404
    assert "HTTP 404" in (result.error or "")


# ── refresh_specs ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_reports_a_written_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from mcp_walmart_ads import specs

    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        specs,
        "fetch_spec",
        lambda source, headers=None, timeout=30.0: {"info": {"version": "1"}, "paths": {}},
    )
    result = await server.refresh_specs("connect:search")
    assert result == {
        "refreshed": 1,
        "total": 1,
        "results": [
            {
                "api": "connect:search",
                "status": "written",
                "version": "1",
                "paths": 0,
                "cached_at": str(tmp_path / "connect" / "search.openapi.json"),
            }
        ],
    }


@pytest.mark.asyncio
async def test_refresh_of_an_unknown_api_is_reported_as_an_error():
    assert "error" in await server.refresh_specs("marketplace:nope")
