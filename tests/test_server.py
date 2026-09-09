from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest

from mcp_walmart_ads import server
from mcp_walmart_ads.config import load_config
from mcp_walmart_ads.platforms import PLATFORM_IDS
from mcp_walmart_ads.resources import ResponseCache
from mcp_walmart_ads.specs import SPEC_IDS
from tests.conftest import raw_config


@pytest.fixture
def loaded(config_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the server's lazy config at a temp file and reset its memo."""
    cfg = load_config(config_file)
    monkeypatch.setattr(server, "_config", cfg)
    monkeypatch.setattr(server, "_cache", ResponseCache(ttl_seconds=cfg.response_cache_ttl))
    monkeypatch.setattr(server, "tokens", server.TokenManager())
    _TMP_CONFIGS.clear()
    _TMP_CONFIGS.append(config_file)
    return cfg


@pytest.fixture
def unconfigured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(server, "_config", None)
    monkeypatch.setattr(server, "_cache", None)
    monkeypatch.setattr(server.config.__globals__["load_config"], "__defaults__", None)
    monkeypatch.setattr(
        server, "load_config", lambda *a, **k: load_config(tmp_path / "absent.json")
    )


_TMP_CONFIGS: list[Path] = []


def tmp_config(data: dict[str, Any]) -> Path:
    """Write a config dict beside the shared fixture's key file."""
    target = _TMP_CONFIGS[0]
    target.write_text(json.dumps(data))
    return target


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
    for resource in await server.mcp.list_resources():
        assert resource.description and resource.description.startswith("[Walmart]")


@pytest.mark.asyncio
async def test_no_parameter_description_carries_the_namespace_tag():
    # A parameter is only read inside its own tool's schema, so the tag would be
    # repetition with nothing to disambiguate.
    offenders = [
        f"{tool.name}.{name}"
        for tool in await server.mcp.list_tools()
        for name, prop in tool.input_schema.get("properties", {}).items()
        if prop.get("description", "").startswith("[Walmart]")
    ]
    assert offenders == [], f"parameters must not repeat the tag: {offenders}"


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
    assert payload["walmart:ads"]["us"]["production"] == {
        "apis": ["walmart:ads:display", "walmart:ads:sponsored-products"]
    }
    assert payload["walmart:marketplace"]["us"]["production"]["advertisers"] == [
        {"id": 7060158, "partner_id": "10001234"},
        {"id": 7060159},
    ]


def test_the_config_resource_surfaces_a_broken_platform_as_an_error(
    write_config, monkeypatch: pytest.MonkeyPatch
):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"].pop("bearer_token")
    cfg = load_config(write_config(data))
    monkeypatch.setattr(server, "_config", cfg)
    monkeypatch.setattr(server, "_cache", ResponseCache())
    payload = json.loads(server.get_config())["platforms"]
    assert "error" in payload["walmart:ads"]
    assert "us" in payload["walmart:marketplace"]


def test_the_config_resource_reports_a_missing_file_instead_of_raising(unconfigured):
    assert "error" in json.loads(server.get_config())


def test_the_apis_resource_lists_the_whole_namespace():
    apis = json.loads(server.get_apis())["apis"]
    assert len(apis) == 31
    assert {a["platform"] for a in apis} == {"walmart:ads", "samsclub:ads", "walmart:marketplace"}


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
    described = await server.describe_endpoint("walmart:marketplace:order-management:getAllOrders")
    assert described["method"] == "GET"


@pytest.mark.asyncio
async def test_list_endpoints_reports_an_unknown_api_as_an_error():
    assert "error" in await server.list_endpoints(api="walmart:marketplace:nope")


@pytest.mark.asyncio
async def test_list_endpoints_reports_an_unknown_platform_as_an_error():
    # The schema enum stops a well-behaved client from ever sending this, but an
    # MCP client is free to ignore the schema, so the runtime guard still has to
    # answer with an error rather than raising. Hence the deliberate type breach.
    assert "error" in await server.list_endpoints(platform="target")  # type: ignore[arg-type]


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
        operation_id="walmart:marketplace:order-management:getAllOrders",
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
        operation_id="samsclub:ads:sponsored-products:AdGroupList",
    )
    assert seen[0].url.host == "advertising.samsclub.com"


@pytest.mark.asyncio
async def test_raw_method_and_path_require_an_api(loaded):
    result = await server.call_endpoint(
        region="us", environment="production", method="GET", path="/api/v1/unpublished"
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
        api="walmart:ads:sponsored-products",
        method="GET",
        path="/api/v1/not-in-the-spec",
    )
    assert result.status_code == 200
    assert str(seen[0].url).endswith("/api/v1/not-in-the-spec")


@pytest.mark.asyncio
async def test_an_unknown_api_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="us", environment="production", api="walmart:ads:nope", method="GET", path="/x"
    )
    assert "unknown api" in (result.error or "")


@pytest.mark.asyncio
async def test_an_unconfigured_region_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="eu",
        environment="production",
        operation_id="walmart:ads:sponsored-products:AdGroupList",
    )
    assert "region" in (result.error or "")


@pytest.mark.asyncio
async def test_a_marketplace_call_without_an_advertiser_id_is_reported_as_an_error(loaded):
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="walmart:marketplace:order-management:getAllOrders",
    )
    assert "advertiser_id" in (result.error or "")


@pytest.mark.asyncio
async def test_a_missing_config_is_reported_as_an_error_not_raised(unconfigured):
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="walmart:ads:sponsored-products:AdGroupList",
    )
    assert "Config file not found" in (result.error or "")


@pytest.mark.asyncio
async def test_a_large_body_is_truncated_and_cached(loaded, monkeypatch: pytest.MonkeyPatch):
    payload = {"rows": [{"i": i, "pad": "x" * 40} for i in range(200)]}
    _transport(monkeypatch, _json_ok(payload))
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="walmart:ads:sponsored-products:AdGroupList",
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
        region="us",
        environment="production",
        operation_id="walmart:ads:sponsored-products:AdGroupList",
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
        region="us",
        environment="production",
        operation_id="walmart:ads:sponsored-products:AdGroupList",
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
        platform="walmart:ads",
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
        platform="walmart:ads",
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
        platform="walmart:ads",
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
        platform="walmart:ads",
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
        platform="walmart:ads",
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
        operation_id="walmart:marketplace:on-request-report-management:downloadReport",
        advertiser_id=7060158,
    )
    assert result.error is None, result.error
    assert any(r.url.host == "marketplace.walmartapis.com" for r in seen)


@pytest.mark.asyncio
async def test_a_download_needs_a_url_an_operation_or_a_path(loaded):
    result = await server.download_file(
        region="us", environment="production", platform="walmart:ads"
    )
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
        platform="walmart:ads",
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
    result = await server.refresh_specs("walmart:ads:sponsored-products")
    assert result == {
        "refreshed": 1,
        "total": 1,
        "results": [
            {
                "api": "walmart:ads:sponsored-products",
                "status": "written",
                "version": "1",
                "paths": 0,
                "cached_at": str(tmp_path / "walmart" / "ads" / "sponsored-products.openapi.json"),
            }
        ],
    }


@pytest.mark.asyncio
async def test_refresh_of_an_unknown_api_is_reported_as_an_error():
    assert "error" in await server.refresh_specs("walmart:marketplace:nope")


# ── schema enums ──────────────────────────────────────────────────────────────


def test_the_platform_literal_matches_the_platform_registry():
    # The Literal is hand-written so it lands in the JSON schema as an enum;
    # this is what stops it drifting from the registry it mirrors.
    assert set(get_args(server.PlatformId)) == set(PLATFORM_IDS)


def test_the_method_literal_covers_every_verb_the_specs_use():
    from mcp_walmart_ads import discovery

    used = {r["method"] for r in discovery.list_endpoints()}
    assert used <= set(get_args(server.HttpMethod))


@pytest.mark.asyncio
async def test_platform_and_method_reach_the_schema_as_enums():
    tools = {t.name: t for t in await server.mcp.list_tools()}

    def enum_of(tool: str, param: str) -> list[str] | None:
        prop = tools[tool].input_schema["properties"][param]
        if "enum" in prop:
            return prop["enum"]
        return next((a["enum"] for a in prop.get("anyOf", []) if "enum" in a), None)

    assert enum_of("list_endpoints", "platform") == list(PLATFORM_IDS)
    assert enum_of("download_file", "platform") == list(PLATFORM_IDS)
    for tool in ("list_endpoints", "call_endpoint", "download_file"):
        assert enum_of(tool, "method") == ["GET", "POST", "PUT", "PATCH", "DELETE"]


@pytest.mark.asyncio
async def test_api_is_deliberately_not_enumerated():
    # 31 values on four tools would cost ~1,270 tokens to duplicate what
    # wmt://apis already returns; the Src: apis lineage tag carries it instead.
    tools = {t.name: t for t in await server.mcp.list_tools()}
    for tool in ("list_endpoints", "describe_endpoint", "call_endpoint", "refresh_specs"):
        prop = tools[tool].input_schema["properties"]["api"]
        assert "enum" not in json.dumps(prop)
        assert "Src: apis" in prop["description"]


@pytest.mark.asyncio
async def test_an_auxiliary_api_is_callable_by_raw_path(loaded, monkeypatch: pytest.MonkeyPatch):
    # Not discoverable, but a valid api for call_endpoint when the config gives
    # it a base URL.
    from tests.conftest import raw_config

    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["base_urls"]["conversions"] = (
        "https://conversions.walmart.test"
    )
    tmp = tmp_config(data)
    monkeypatch.setattr(server, "_config", load_config(tmp))
    monkeypatch.setattr(server, "_cache", ResponseCache())
    seen = _transport(monkeypatch, _json_ok({"ok": True}))
    result = await server.call_endpoint(
        region="us",
        environment="production",
        api="walmart:ads:conversions",
        method="POST",
        path="/v1/events",
    )
    assert result.status_code == 200
    assert seen[0].url.host == "conversions.walmart.test"


# ── description hygiene ───────────────────────────────────────────────────────

# Anything shaped like an id in prose: two or three colon-separated segments of
# lowercase words. Catches a stale example long after the rename that made it
# stale, which review did not.
_ID_IN_PROSE = re.compile(r"\b[a-z][a-z0-9-]*:[a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)?\b")


def _all_descriptions(tools, resources, templates) -> dict[str, str]:
    out: dict[str, str] = {"<instructions>": server.mcp.instructions or ""}
    for t in tools:
        out[t.name] = t.description or ""
        for name, prop in t.input_schema.get("properties", {}).items():
            out[f"{t.name}.{name}"] = prop.get("description", "")
    for r in resources:
        out[str(r.uri)] = r.description or ""
    for t in templates:
        out[str(t.uri_template)] = t.description or ""
    return out


@pytest.mark.asyncio
async def test_no_description_names_an_api_or_platform_that_does_not_exist():
    descriptions = _all_descriptions(
        await server.mcp.list_tools(),
        await server.mcp.list_resources(),
        await server.mcp.list_resource_templates(),
    )
    known = set(SPEC_IDS) | set(PLATFORM_IDS)
    # Ids appear inside resource URIs and prose that is not an id at all; only
    # candidates whose first segment is a real retailer are held to the namespace.
    retailers = {p.split(":")[0] for p in PLATFORM_IDS}
    stale: list[str] = []
    for where, text in descriptions.items():
        for candidate in _ID_IN_PROSE.findall(text):
            if candidate.split(":")[0] not in retailers:
                continue
            if candidate not in known:
                stale.append(f"{where}: {candidate}")
    assert stale == [], f"descriptions name ids that do not exist: {stale}"


@pytest.mark.asyncio
async def test_no_description_uses_a_pre_0_2_platform_name():
    descriptions = _all_descriptions(
        await server.mcp.list_tools(),
        await server.mcp.list_resources(),
        await server.mcp.list_resource_templates(),
    )
    offenders = [
        f"{where}: {legacy}"
        for where, text in descriptions.items()
        for legacy in ("connect:", "samsclub:sponsored", "marketplace:order")
        if legacy in text and f"walmart:{legacy}" not in text
    ]
    assert offenders == [], f"pre-0.2 ids left in descriptions: {offenders}"


@pytest.mark.asyncio
async def test_every_description_is_namespaced_and_non_empty():
    descriptions = _all_descriptions(
        await server.mcp.list_tools(),
        await server.mcp.list_resources(),
        await server.mcp.list_resource_templates(),
    )
    for where, text in descriptions.items():
        assert text, f"{where} has no description"
        # Tools and resources carry the tag; parameters deliberately do not, and
        # "<instructions>" is server-level prose.
        if "." not in where and where != "<instructions>":
            assert text.startswith("[Walmart]"), f"{where} is not namespaced"


@pytest.mark.asyncio
async def test_every_parameter_naming_a_configured_entity_declares_its_lineage():
    # AGENTS.md: parameters referring to entities this server owns carry Src:.
    expected = {
        "region": "Src: config",
        "environment": "Src: config",
        "advertiser_id": "Src: config",
        "api": "Src: apis",
        "platform": "Src: apis",
        "operation_id": "Src: operations",
    }
    for tool in await server.mcp.list_tools():
        for name, prop in tool.input_schema.get("properties", {}).items():
            tag = expected.get(name)
            if tag is None:
                continue
            assert tag in prop.get("description", ""), f"{tool.name}.{name} lacks '{tag}'"


# ── config health reported to a caller ────────────────────────────────────────


def _with_broken_samsclub(monkeypatch: pytest.MonkeyPatch, write_config) -> None:
    data = raw_config()
    data["platforms"]["samsclub:ads"]["regions"]["us"]["production"].pop("bearer_token")
    cfg = load_config(write_config(data))
    monkeypatch.setattr(server, "_config", cfg)
    monkeypatch.setattr(server, "_cache", ResponseCache())


def test_the_config_resource_leads_with_what_is_usable(loaded):
    payload = json.loads(server.get_config())
    assert list(payload)[0] == "usable"
    assert set(payload["usable"]) == {"walmart:ads", "walmart:marketplace", "samsclub:ads"}
    assert "unusable" not in payload


def test_the_config_resource_names_an_unusable_platform_and_its_file(
    monkeypatch: pytest.MonkeyPatch, write_config
):
    _with_broken_samsclub(monkeypatch, write_config)
    payload = json.loads(server.get_config())
    assert payload["usable"] == ["walmart:ads", "walmart:marketplace"]
    entry = payload["unusable"]["samsclub:ads"]
    assert entry["source"].endswith("config.json")
    assert entry["problems"] == 1


def test_the_config_resource_reports_unparsed_files(
    tmp_path: Path, key_file: Path, monkeypatch: pytest.MonkeyPatch
):
    data = raw_config()
    moved = {"walmart:marketplace": data["platforms"].pop("walmart:marketplace")}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    (tmp_path / "config.d").mkdir()
    (tmp_path / "config.d" / "mp.json").write_text("{ not json")
    assert key_file.exists() and moved
    monkeypatch.setattr(server, "_config", load_config(path))
    monkeypatch.setattr(server, "_cache", ResponseCache())
    payload = json.loads(server.get_config())
    assert "walmart:marketplace" not in payload["usable"]
    assert list(payload["unparsed_files"])[0].endswith("mp.json")


@pytest.mark.asyncio
async def test_a_call_to_an_unusable_platform_tells_the_caller_what_to_do(
    monkeypatch: pytest.MonkeyPatch, write_config
):
    _with_broken_samsclub(monkeypatch, write_config)
    result = await server.call_endpoint(
        region="us",
        environment="production",
        operation_id="samsclub:ads:sponsored-products:LatestReportDate",
    )
    error = result.error or ""
    assert "samsclub:ads is not usable" in error
    assert "restart" in error
    assert "Usable now: walmart:ads, walmart:marketplace" in error


@pytest.mark.asyncio
async def test_discovery_stays_silent_about_a_broken_platform(
    monkeypatch: pytest.MonkeyPatch, write_config
):
    # Deliberate: discovery must work with no credentials at all, so it never
    # consults the config and cannot warn. The call-time error carries the news.
    _with_broken_samsclub(monkeypatch, write_config)
    result = await server.list_endpoints(platform="samsclub:ads")
    assert result["count"] > 0
    assert "error" not in result
