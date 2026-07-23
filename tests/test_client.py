from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_walmart_ads.client import _build_headers, download_file
from mcp_walmart_ads.config import EnvConfig


def _make_env_cfg() -> EnvConfig:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return EnvConfig(
        consumer_id="test-consumer",
        private_key_pem=pem,
        private_key_version="1",
        bearer_token="test-token",
        base_urls={
            "search": "https://search.example.com/api/v1",
            "display": "https://display.example.com/api/v1",
        },
    )


def test_build_headers_contains_required_keys() -> None:
    cfg = _make_env_cfg()
    headers = _build_headers(cfg)
    assert "WM_CONSUMER.ID" in headers
    assert "WM_CONSUMER.INTIMESTAMP" in headers
    assert "WM_SEC.KEY_VERSION" in headers
    assert "WM_SEC.AUTH_SIGNATURE" in headers
    assert "WM_QOS.CORRELATION_ID" in headers
    assert headers["Authorization"] == "Bearer test-token"


def test_build_headers_consumer_id() -> None:
    cfg = _make_env_cfg()
    headers = _build_headers(cfg)
    assert headers["WM_CONSUMER.ID"] == "test-consumer"


def test_build_headers_correlation_id_is_uuid() -> None:
    import re

    cfg = _make_env_cfg()
    headers = _build_headers(cfg)
    uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    assert re.match(uuid_pattern, headers["WM_QOS.CORRELATION_ID"])


def test_build_headers_omits_advertiser_and_tenant_by_default() -> None:
    cfg = _make_env_cfg()
    headers = _build_headers(cfg)
    assert "X-Advertiser-ID" not in headers
    assert "wap-tenant-id" not in headers


def test_build_headers_includes_advertiser_and_tenant_when_passed() -> None:
    cfg = _make_env_cfg()
    headers = _build_headers(cfg, advertiser_id=600001, tenant="WMT_CA")
    assert headers["X-Advertiser-ID"] == "600001"
    assert headers["wap-tenant-id"] == "WMT_CA"


@pytest.mark.asyncio
async def test_execute_request_builds_correct_url() -> None:
    from mcp_walmart_ads.client import execute_request

    cfg = _make_env_cfg()
    mock_response = MagicMock()
    mock_response.json.return_value = {"campaigns": []}
    mock_response.status_code = 200

    mock_response.request.url = (
        "https://search.example.com/api/v1/api/v1/campaigns?advertiserId=123"
    )

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await execute_request(
            cfg=cfg,
            ad_type="search",
            method="GET",
            path="/api/v1/campaigns",
            params={"advertiserId": 123},
        )

    assert result.status_code == 200
    assert result.body == {"campaigns": []}
    call_kwargs = mock_client.request.call_args
    assert call_kwargs.kwargs["url"] == "https://search.example.com/api/v1/api/v1/campaigns"
    assert call_kwargs.kwargs["method"] == "GET"
    assert "curl -X GET" in result.curl
    assert "WM_SEC.AUTH_SIGNATURE" in result.curl
    headers = call_kwargs.kwargs["headers"]
    assert "X-Advertiser-ID" not in headers
    assert "wap-tenant-id" not in headers


@pytest.mark.asyncio
async def test_execute_request_forwards_advertiser_and_tenant_headers() -> None:
    from mcp_walmart_ads.client import execute_request

    cfg = _make_env_cfg()
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.status_code = 200
    mock_response.request.url = "https://search.example.com/api/v1/api/v1/campaigns"

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await execute_request(
            cfg=cfg,
            ad_type="search",
            method="GET",
            path="/api/v1/campaigns",
            advertiser_id=600001,
            tenant="WMT_CA",
        )

    headers = mock_client.request.call_args.kwargs["headers"]
    assert headers["X-Advertiser-ID"] == "600001"
    assert headers["wap-tenant-id"] == "WMT_CA"


@pytest.mark.asyncio
async def test_download_file_uses_full_url_with_auth_headers() -> None:
    cfg = _make_env_cfg()
    mock_response = MagicMock()
    mock_response.content = b"\x1f\x8b fake gzip"
    mock_response.status_code = 200
    mock_response.request.url = (
        "https://advertising.walmart.com/display/file/abc-123?advertiserId=600001"
    )
    mock_response.headers = {}

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await download_file(
            cfg=cfg,
            url="https://advertising.walmart.com/display/file/abc-123",
            params={"advertiserId": 600001},
        )

    assert result.status_code == 200
    assert result.content == b"\x1f\x8b fake gzip"
    assert result.urls == "https://advertising.walmart.com/display/file/abc-123?advertiserId=600001"
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.args[0] == "https://advertising.walmart.com/display/file/abc-123"
    assert call_kwargs.kwargs["params"] == {"advertiserId": 600001}
    headers = call_kwargs.kwargs["headers"]
    assert "WM_SEC.AUTH_SIGNATURE" in headers
    assert "Authorization" in headers
    assert "Content-Type" not in headers
    assert "X-Advertiser-ID" not in headers
    assert "wap-tenant-id" not in headers


@pytest.mark.asyncio
async def test_download_file_forwards_advertiser_and_tenant_headers() -> None:
    cfg = _make_env_cfg()
    mock_response = MagicMock()
    mock_response.content = b"data"
    mock_response.status_code = 200
    mock_response.request.url = "https://advertising.walmart.com/display/file/abc-123"
    mock_response.headers = {}

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await download_file(
            cfg=cfg,
            url="https://advertising.walmart.com/display/file/abc-123",
            params={"advertiserId": 600001},
            advertiser_id=600001,
            tenant="WMT_MX",
        )

    headers = mock_client.get.call_args.kwargs["headers"]
    assert headers["X-Advertiser-ID"] == "600001"
    assert headers["wap-tenant-id"] == "WMT_MX"


@pytest.mark.asyncio
async def test_download_file_follows_relative_redirect_keeping_init_headers() -> None:
    cfg = _make_env_cfg()
    start = "https://advertising.walmart.com/mx/file/abc-123"
    final = "https://advertising.walmart.com/mx/sp/api/file/abc-123"

    redirect = MagicMock()
    redirect.status_code = 301
    redirect.content = b""
    redirect.headers = {"Location": "/mx/sp/api/file/abc-123"}
    redirect.url = start
    redirect.request.url = start

    ok = MagicMock()
    ok.status_code = 200
    ok.content = b'"adSpend","date"\n'
    ok.headers = {}
    ok.request.url = final

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[redirect, ok])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await download_file(
            cfg=cfg,
            url=start,
            advertiser_id=600001,
            tenant="WMT_MX",
        )

    assert result.status_code == 200
    assert result.content == b'"adSpend","date"\n'
    assert result.urls == f"{start},{final}"
    assert mock_client.get.call_count == 2

    first_headers = mock_client.get.call_args_list[0].kwargs["headers"]
    second_headers = mock_client.get.call_args_list[1].kwargs["headers"]
    assert second_headers is first_headers
    assert second_headers["Authorization"] == "Bearer test-token"
    assert second_headers["wap-tenant-id"] == "WMT_MX"
    assert mock_client.get.call_args_list[0].kwargs["params"] is None
    assert mock_client.get.call_args_list[1].args[0] == final
    assert mock_client.get.call_args_list[1].kwargs["params"] is None


@pytest.mark.asyncio
async def test_download_file_strips_authorization_on_cross_host_redirect() -> None:
    cfg = _make_env_cfg()
    start = "https://advertising.walmart.com/mx/file/abc-123"
    final = "https://cdn.example.com/files/abc-123"

    redirect = MagicMock()
    redirect.status_code = 302
    redirect.content = b""
    redirect.headers = {"Location": final}
    redirect.url = start
    redirect.request.url = start

    ok = MagicMock()
    ok.status_code = 200
    ok.content = b"payload"
    ok.headers = {}
    ok.request.url = final

    with patch("mcp_walmart_ads.client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[redirect, ok])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await download_file(cfg=cfg, url=start, tenant="WMT_MX")

    assert result.status_code == 200
    assert result.urls == f"{start},{final}"
    second_headers = mock_client.get.call_args_list[1].kwargs["headers"]
    assert "Authorization" not in second_headers
    assert "WM_SEC.AUTH_SIGNATURE" in second_headers
    assert second_headers["wap-tenant-id"] == "WMT_MX"
