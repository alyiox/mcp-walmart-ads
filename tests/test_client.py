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


@pytest.mark.asyncio
async def test_download_file_uses_full_url_with_auth_headers() -> None:
    cfg = _make_env_cfg()
    mock_response = MagicMock()
    mock_response.content = b"\x1f\x8b fake gzip"
    mock_response.status_code = 200

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
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.args[0] == "https://advertising.walmart.com/display/file/abc-123"
    assert call_kwargs.kwargs["params"] == {"advertiserId": 600001}
    headers = call_kwargs.kwargs["headers"]
    assert "WM_SEC.AUTH_SIGNATURE" in headers
    assert "Authorization" in headers
    assert "Content-Type" not in headers
