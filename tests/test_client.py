from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from mcp_walmart_ads import client
from mcp_walmart_ads.auth import TokenManager
from mcp_walmart_ads.client import (
    RequestError,
    accept_for,
    build_curl,
    headers_for_redirect,
    redact,
    requires_partner_id,
    resolve_path,
)
from mcp_walmart_ads.config import OAuth2Env, SignatureEnv
from mcp_walmart_ads.discovery import Operation


def _operation(
    raw: dict[str, Any], *, api: str = "walmart:marketplace:order-management"
) -> Operation:
    return Operation(
        operation_id="Op", api=api, method="get", path="/v3/orders", summary="", tags=(), raw=raw
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


def _ok(payload: Any = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v3/token"):
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})
        return httpx.Response(200, json=payload if payload is not None else {"ok": True})

    return handler


# ── path shaping ──────────────────────────────────────────────────────────────


def test_path_placeholders_are_substituted():
    assert resolve_path("/v3/orders/{id}", {"id": "123"}) == ("/v3/orders/123", {})


def test_an_unsubstituted_placeholder_is_an_error_naming_it():
    with pytest.raises(RequestError) as excinfo:
        resolve_path("/v3/orders/{purchaseOrderId}", None)
    assert "purchaseOrderId" in str(excinfo.value)
    assert "path_params" in str(excinfo.value)


def test_a_query_string_baked_into_a_path_is_lifted_out():
    path, params = resolve_path("/v3/feeds?feedType=MP_ITEM&requestType=x", None)
    assert path == "/v3/feeds"
    assert params == {"feedType": "MP_ITEM", "requestType": "x"}


# ── Accept negotiation ────────────────────────────────────────────────────────


def test_accept_prefers_json_when_offered():
    op = _operation({"responses": {"200": {"content": {"text/csv": {}, "application/json": {}}}}})
    assert accept_for(op, fallback="*/*") == "application/json"


def test_accept_names_concrete_types_for_binary_endpoints():
    op = _operation({"responses": {"200": {"content": {"application/pdf": {}, "image/png": {}}}}})
    assert accept_for(op, fallback="*/*") == "application/pdf, image/png"


def test_accept_skips_wildcards_and_falls_back_when_nothing_concrete_is_declared():
    op = _operation({"responses": {"200": {"content": {"*/*": {}}}}})
    assert accept_for(op, fallback="application/json") == "application/json"
    assert accept_for(None, fallback="*/*") == "*/*"


# ── partner id ────────────────────────────────────────────────────────────────


def test_a_required_partner_id_header_is_detected():
    op = _operation({"parameters": [{"in": "header", "name": "WM_PARTNER_ID", "required": True}]})
    assert requires_partner_id(op) == "WM_PARTNER_ID"


def test_an_optional_partner_id_header_is_not_required():
    op = _operation({"parameters": [{"in": "header", "name": "WM_PARTNER_ID"}]})
    assert requires_partner_id(op) is None
    assert requires_partner_id(None) is None


@pytest.mark.asyncio
async def test_an_operation_requiring_partner_id_fails_when_the_seller_has_none(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    op = _operation({"parameters": [{"in": "header", "name": "WM_PARTNER_ID", "required": True}]})
    with pytest.raises(RequestError) as excinfo:
        await client.execute_request(
            cfg=oauth2_env,
            api=op.api,
            method="get",
            path="/v3/x",
            operation=op,
            advertiser_id=7060159,  # this one has no partner_id
            tokens=TokenManager(),
        )
    assert "partner_id" in str(excinfo.value)


# ── header assembly ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signature_platform_sends_the_signature_set_and_bearer(signature_env: SignatureEnv):
    headers = await client.auth_headers(signature_env)
    assert headers["WM_CONSUMER.ID"] == "connect-consumer"
    assert headers["Authorization"] == "Bearer connect-bearer"
    assert headers["WM_SEC.KEY_VERSION"] == "1"
    assert headers["WM_SEC.AUTH_SIGNATURE"]
    assert int(headers["WM_CONSUMER.INTIMESTAMP"]) > 0
    assert "WM_SEC.ACCESS_TOKEN" not in headers


@pytest.mark.asyncio
async def test_advertiser_and_tenant_are_headers_on_a_signature_platform(
    signature_env: SignatureEnv,
):
    headers = await client.auth_headers(signature_env, advertiser_id=99, tenant="WMT_CA")
    assert headers["X-Advertiser-ID"] == "99"
    assert headers["wap-tenant-id"] == "WMT_CA"


@pytest.mark.asyncio
async def test_advertiser_and_tenant_are_omitted_by_default(signature_env: SignatureEnv):
    headers = await client.auth_headers(signature_env)
    assert "X-Advertiser-ID" not in headers
    assert "wap-tenant-id" not in headers


@pytest.mark.asyncio
async def test_correlation_id_is_always_present_and_unique(signature_env: SignatureEnv):
    first = await client.auth_headers(signature_env)
    second = await client.auth_headers(signature_env)
    assert first["WM_QOS.CORRELATION_ID"] != second["WM_QOS.CORRELATION_ID"]


@pytest.mark.asyncio
async def test_oauth2_platform_sends_the_access_token_not_a_client_secret(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    headers = await client.auth_headers(
        oauth2_env,
        tokens=TokenManager(),
        advertiser_id=7060158,
    )
    assert headers["WM_SEC.ACCESS_TOKEN"] == "tok-1"
    assert headers["WM_SVC.NAME"] == "Walmart Marketplace"
    assert "Authorization" not in headers
    assert "secret-1" not in str(headers)


@pytest.mark.asyncio
async def test_market_and_global_version_come_from_the_operation(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    op = _operation(
        {
            "parameters": [
                {"in": "header", "name": "WM_MARKET", "schema": {"enum": ["us"]}},
                {"in": "header", "name": "WM_GLOBAL_VERSION", "schema": {"enum": ["3.1"]}},
            ]
        }
    )
    headers = await client.auth_headers(
        oauth2_env,
        operation=op,
        tokens=TokenManager(),
        advertiser_id=7060158,
    )
    assert headers["WM_MARKET"] == "us"
    assert headers["WM_GLOBAL_VERSION"] == "3.1"


@pytest.mark.asyncio
async def test_global_version_is_omitted_when_the_operation_does_not_declare_it(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    headers = await client.auth_headers(
        oauth2_env,
        operation=_operation({}),
        tokens=TokenManager(),
        advertiser_id=7060158,
    )
    assert "WM_GLOBAL_VERSION" not in headers
    assert "WM_MARKET" not in headers


@pytest.mark.asyncio
async def test_partner_id_is_sent_when_the_seller_has_one(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    headers = await client.auth_headers(
        oauth2_env,
        tokens=TokenManager(),
        advertiser_id=7060158,
    )
    assert headers["WM_PARTNER_ID"] == "10001234"


@pytest.mark.asyncio
async def test_sandbox_header_is_sent_on_the_sandbox_environment(
    credential, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    env = OAuth2Env(
        platform="walmart:marketplace",
        region="us",
        environment="sandbox",
        credentials=(credential,),
        by_advertiser={7060158: credential},
        advertiser_records={},
    )
    headers = await client.auth_headers(
        env,
        tokens=TokenManager(),
        advertiser_id=7060158,
    )
    assert headers["WM_SANDBOX"] == "v2"


@pytest.mark.asyncio
async def test_an_oauth2_platform_without_an_advertiser_id_is_an_error(oauth2_env: OAuth2Env):
    with pytest.raises(RequestError) as excinfo:
        await client.auth_headers(oauth2_env, tokens=TokenManager())
    assert "advertiser_id" in str(excinfo.value)


# ── redaction and curl ────────────────────────────────────────────────────────


def test_redaction_replaces_every_kind_of_credential():
    redacted = redact(
        {
            "Authorization": "Bearer super-secret",
            "WM_SEC.ACCESS_TOKEN": "tok-abc",
            "WM_SEC.AUTH_SIGNATURE": "sig-abc",
            "WM_CONSUMER.ID": "consumer-1",
        }
    )
    assert redacted["Authorization"] == "Bearer $WM_BEARER_TOKEN"
    assert redacted["WM_SEC.ACCESS_TOKEN"] == "$WM_ACCESS_TOKEN"
    assert redacted["WM_SEC.AUTH_SIGNATURE"] == "$WM_AUTH_SIGNATURE"
    assert redacted["WM_CONSUMER.ID"] == "consumer-1"


def test_curl_carries_no_credential_material():
    curl = build_curl(
        "post",
        "https://x.test/a",
        {"Authorization": "Bearer super-secret", "WM_SEC.AUTH_SIGNATURE": "sig-abc"},
        {"k": "v"},
    )
    assert "super-secret" not in curl
    assert "sig-abc" not in curl
    assert curl.startswith("curl -X POST 'https://x.test/a'")
    assert '-d \'{"k": "v"}\'' in curl


# ── execution ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_signature_call_targets_the_configured_base_url(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _ok())
    await client.execute_request(
        cfg=signature_env,
        api="walmart:ads:sponsored-products",
        method="get",
        path="/api/v1/campaigns",
    )
    assert str(seen[0].url) == "https://advertising.walmart.com/api/v1/campaigns"


@pytest.mark.asyncio
async def test_a_marketplace_call_targets_the_fixed_host(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _ok())
    await client.execute_request(
        cfg=oauth2_env,
        api="walmart:marketplace:order-management",
        method="get",
        path="/v3/orders",
        advertiser_id=7060158,
        tokens=TokenManager(),
    )
    assert str(seen[-1].url) == "https://marketplace.walmartapis.com/v3/orders"


@pytest.mark.asyncio
async def test_baked_and_explicit_query_params_are_merged(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    seen = _transport(monkeypatch, _ok())
    await client.execute_request(
        cfg=signature_env,
        api="walmart:ads:sponsored-products",
        method="get",
        path="/api/v1/x?baked=1",
        params={"explicit": "2"},
    )
    assert dict(seen[0].url.params) == {"baked": "1", "explicit": "2"}


@pytest.mark.asyncio
async def test_a_non_json_response_body_is_returned_as_text(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    _transport(monkeypatch, handler)
    response = await client.execute_request(
        cfg=signature_env, api="walmart:ads:sponsored-products", method="get", path="/x"
    )
    assert response.body == "not json"


@pytest.mark.asyncio
async def test_a_401_is_retried_once_with_a_fresh_token_on_marketplace(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    calls = {"api": 0, "token": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/v3/token"):
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok-{calls['token']}"})
        calls["api"] += 1
        if calls["api"] == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    _transport(monkeypatch, handler)
    response = await client.execute_request(
        cfg=oauth2_env,
        api="walmart:marketplace:order-management",
        method="get",
        path="/v3/orders",
        advertiser_id=7060158,
        tokens=TokenManager(),
    )
    assert response.status_code == 200
    assert calls == {"api": 2, "token": 2}


@pytest.mark.asyncio
async def test_a_401_is_not_retried_on_a_signature_platform(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "denied"})

    seen = _transport(monkeypatch, handler)
    response = await client.execute_request(
        cfg=signature_env, api="walmart:ads:sponsored-products", method="get", path="/x"
    )
    assert response.status_code == 401
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_a_file_path_switches_the_request_to_multipart(
    oauth2_env: OAuth2Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    feed = tmp_path / "feed.json"
    feed.write_text('{"items": []}')
    seen = _transport(monkeypatch, _ok())
    await client.execute_request(
        cfg=oauth2_env,
        api="walmart:marketplace:feed-management",
        method="post",
        path="/v3/feeds",
        params={"feedType": "MP_ITEM"},
        file_path=str(feed),
        advertiser_id=7060158,
        tokens=TokenManager(),
    )
    request = seen[-1]
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="file"' in request.content
    assert b"feed.json" in request.content


@pytest.mark.asyncio
async def test_an_unreadable_upload_file_is_an_error(
    oauth2_env: OAuth2Env, monkeypatch: pytest.MonkeyPatch
):
    _transport(monkeypatch, _ok())
    with pytest.raises(RequestError) as excinfo:
        await client.execute_request(
            cfg=oauth2_env,
            api="walmart:marketplace:feed-management",
            method="post",
            path="/v3/feeds",
            file_path="/nonexistent/feed.json",
            advertiser_id=7060158,
            tokens=TokenManager(),
        )
    assert "cannot read" in str(excinfo.value)


# ── redirects ─────────────────────────────────────────────────────────────────


def test_a_relative_location_keeps_the_init_headers():
    init = {"Authorization": "Bearer x", "WM_CONSUMER.ID": "c"}
    assert (
        headers_for_redirect(
            init,
            location="/next",
            current_url="https://a.test/one",
            next_url="https://a.test/next",
        )
        is init
    )


def test_a_same_host_absolute_location_keeps_the_init_headers():
    init = {"Authorization": "Bearer x"}
    assert (
        headers_for_redirect(
            init,
            location="https://a.test/next",
            current_url="https://a.test/one",
            next_url="https://a.test/next",
        )
        is init
    )


def test_a_cross_host_location_drops_every_credential_header():
    kept = headers_for_redirect(
        {
            "Authorization": "Bearer x",
            "WM_SEC.ACCESS_TOKEN": "t",
            "WM_SEC.AUTH_SIGNATURE": "s",
            "Accept": "*/*",
        },
        location="https://storage.test/blob",
        current_url="https://a.test/one",
        next_url="https://storage.test/blob",
    )
    assert kept == {"Accept": "*/*"}


@pytest.mark.asyncio
async def test_download_follows_a_redirect_and_records_the_hops(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "advertising.walmart.com":
            return httpx.Response(302, headers={"location": "https://storage.test/blob"})
        assert "authorization" not in {k.casefold() for k in request.headers}
        return httpx.Response(200, content=b"payload", headers={"content-type": "text/csv"})

    _transport(monkeypatch, handler)
    response = await client.download(
        cfg=signature_env,
        api="walmart:ads:sponsored-products",
        url="https://advertising.walmart.com/report/1",
    )
    assert response.status_code == 200
    assert response.content == b"payload"
    assert response.content_type == "text/csv"
    assert response.urls == "https://advertising.walmart.com/report/1 → https://storage.test/blob"


@pytest.mark.asyncio
async def test_download_stops_after_the_redirect_limit(
    signature_env: SignatureEnv, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    seen = _transport(monkeypatch, handler)
    response = await client.download(
        cfg=signature_env,
        api="walmart:ads:sponsored-products",
        url="https://advertising.walmart.com/report/1",
    )
    assert response.status_code == 302
    assert len(seen) == client._MAX_REDIRECTS + 1


@pytest.mark.asyncio
async def test_download_requires_a_url_or_an_api_with_a_path(signature_env: SignatureEnv):
    with pytest.raises(RequestError):
        await client.download(cfg=signature_env, path="/x")
