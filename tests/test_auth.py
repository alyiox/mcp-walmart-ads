from __future__ import annotations

import asyncio
import base64
import time

import httpx
import pytest

from mcp_walmart_ads import auth
from mcp_walmart_ads.auth import (
    DEFAULT_EXPIRES_IN,
    REFRESH_MARGIN_SECONDS,
    AuthError,
    Token,
    TokenManager,
    basic_auth_header,
    generate_signature,
    token_url,
)
from mcp_walmart_ads.config import Credential

# ── signature ─────────────────────────────────────────────────────────────────


def test_signature_is_nonempty_base64(private_key_pem: str):
    sig = generate_signature("consumer-1", private_key_pem)
    assert sig.signature
    assert base64.b64decode(sig.signature)


def test_signature_timestamp_is_milliseconds(private_key_pem: str):
    sig = generate_signature("consumer-1", private_key_pem)
    assert abs(int(sig.timestamp) - int(time.time() * 1000)) < 60_000


def test_key_version_defaults_to_one_and_is_carried_through(private_key_pem: str):
    assert generate_signature("c", private_key_pem).key_version == "1"
    assert generate_signature("c", private_key_pem, "4").key_version == "4"


def test_successive_signatures_differ_because_the_timestamp_is_signed(private_key_pem: str):
    first = generate_signature("consumer-1", private_key_pem)
    time.sleep(0.002)
    second = generate_signature("consumer-1", private_key_pem)
    assert first.timestamp != second.timestamp
    assert first.signature != second.signature


def test_unreadable_private_key_raises_authenticaton_error():
    with pytest.raises(AuthError) as excinfo:
        generate_signature("consumer-1", "not a pem")
    assert "PEM" in str(excinfo.value)


# ── oauth2 token plumbing ─────────────────────────────────────────────────────


def test_basic_auth_header_encodes_id_and_secret(credential: Credential):
    header = basic_auth_header(credential)
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
    assert decoded == "cid-1:secret-1"


def test_token_url_is_the_bare_environment_host():
    assert token_url("marketplace", "production") == "https://marketplace.walmartapis.com/v3/token"
    assert token_url("marketplace", "sandbox") == "https://sandbox.walmartapis.com/v3/token"


def test_token_url_rejects_a_platform_without_fixed_hosts():
    with pytest.raises(AuthError):
        token_url("connect", "production")


def test_token_freshness_respects_the_refresh_margin():
    now = 1_000.0
    assert Token("t", now + REFRESH_MARGIN_SECONDS + 1).is_fresh(now=now)
    assert not Token("t", now + REFRESH_MARGIN_SECONDS - 1).is_fresh(now=now)
    assert not Token("t", now - 1).is_fresh(now=now)


def _token_response(handler_calls: list[httpx.Request], expires_in: object = 900):
    payload: dict[str, object] = {"access_token": "tok-1"}
    if expires_in is not None:
        payload["expires_in"] = expires_in

    async def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        return httpx.Response(200, json=payload)

    return handler


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    original = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return original(*args, transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_fetch_token_sends_basic_auth_and_the_client_credentials_grant(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    token = await auth.fetch_token(credential, "marketplace", "production")
    assert token.access_token == "tok-1"
    request = calls[0]
    assert str(request.url) == "https://marketplace.walmartapis.com/v3/token"
    assert request.headers["Authorization"] == basic_auth_header(credential)
    assert request.content == b"grant_type=client_credentials"
    assert request.headers["WM_SVC.NAME"] == "Walmart Marketplace"


@pytest.mark.asyncio
async def test_missing_expires_in_falls_back_to_the_documented_lifetime(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    _patch_transport(monkeypatch, _token_response([], expires_in=None))
    before = time.monotonic()
    token = await auth.fetch_token(credential, "marketplace", "production")
    assert token.expires_at >= before + DEFAULT_EXPIRES_IN


@pytest.mark.asyncio
async def test_non_200_token_response_raises_with_the_body(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden-detail")

    _patch_transport(monkeypatch, handler)
    with pytest.raises(AuthError) as excinfo:
        await auth.fetch_token(credential, "marketplace", "production")
    assert "403" in str(excinfo.value)
    assert "forbidden-detail" in str(excinfo.value)


@pytest.mark.asyncio
async def test_token_response_without_an_access_token_raises(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    _patch_transport(monkeypatch, handler)
    with pytest.raises(AuthError) as excinfo:
        await auth.fetch_token(credential, "marketplace", "production")
    assert "no access_token" in str(excinfo.value)


@pytest.mark.asyncio
async def test_non_json_token_response_raises(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    _patch_transport(monkeypatch, handler)
    with pytest.raises(AuthError) as excinfo:
        await auth.fetch_token(credential, "marketplace", "production")
    assert "not JSON" in str(excinfo.value)


# ── token cache ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_fresh_cached_token_is_reused(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    manager = TokenManager()
    for _ in range(3):
        await manager.access_token(
            credential, platform="marketplace", region="us", environment="production"
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_force_refresh_discards_the_cached_token(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    manager = TokenManager()
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="production"
    )
    await manager.access_token(
        credential,
        platform="marketplace",
        region="us",
        environment="production",
        force_refresh=True,
    )
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_the_cache_key_separates_platform_region_environment_and_credential(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    manager = TokenManager()
    other = Credential(client_id="cid-2", client_secret="s", advertisers=credential.advertisers)
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="production"
    )
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="sandbox"
    )
    await manager.access_token(
        credential, platform="marketplace", region="ca", environment="production"
    )
    await manager.access_token(other, platform="marketplace", region="us", environment="production")
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_region_lookup_in_the_cache_key_is_case_insensitive(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    manager = TokenManager()
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="production"
    )
    await manager.access_token(
        credential, platform="marketplace", region="US", environment="production"
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_concurrent_callers_fetch_the_token_once(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})

    _patch_transport(monkeypatch, handler)
    manager = TokenManager()
    await asyncio.gather(
        *[
            manager.access_token(
                credential, platform="marketplace", region="us", environment="production"
            )
            for _ in range(8)
        ]
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_invalidate_forces_the_next_call_to_refetch(
    credential: Credential, monkeypatch: pytest.MonkeyPatch
):
    calls: list[httpx.Request] = []
    _patch_transport(monkeypatch, _token_response(calls))
    manager = TokenManager()
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="production"
    )
    manager.invalidate(credential, platform="marketplace", region="US", environment="production")
    await manager.access_token(
        credential, platform="marketplace", region="us", environment="production"
    )
    assert len(calls) == 2
