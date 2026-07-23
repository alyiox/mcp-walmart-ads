from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .auth import generate_signature
from .config import EnvConfig

_MAX_REDIRECTS = 5
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    body: Any
    request_id: str
    curl: str


@dataclass(frozen=True)
class DownloadResponse:
    status_code: int
    content: bytes
    request_id: str
    urls: str


def _build_headers(
    cfg: EnvConfig,
    *,
    advertiser_id: int | None = None,
    tenant: str | None = None,
) -> dict[str, str]:
    sig = generate_signature(cfg.consumer_id, cfg.private_key_pem, cfg.private_key_version)
    headers = {
        "WM_CONSUMER.ID": cfg.consumer_id,
        "WM_CONSUMER.INTIMESTAMP": sig.timestamp,
        "WM_SEC.KEY_VERSION": sig.key_version,
        "WM_SEC.AUTH_SIGNATURE": sig.signature,
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "Authorization": f"Bearer {cfg.bearer_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if advertiser_id is not None:
        headers["X-Advertiser-ID"] = str(advertiser_id)
    if tenant:
        headers["wap-tenant-id"] = tenant
    return headers


def build_curl(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | list[Any] | None = None,
) -> str:
    parts = [f"curl -X {method.upper()} '{url}'"]
    for k, v in headers.items():
        parts.append(f"  -H '{k}: {v}'")
    if body is not None:
        parts.append(f"  -d '{json.dumps(body)}'")
    return " \\\n".join(parts)


async def execute_request(
    cfg: EnvConfig,
    ad_type: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | list[Any] | None = None,
    advertiser_id: int | None = None,
    tenant: str | None = None,
) -> ApiResponse:
    base_url = cfg.base_urls[ad_type].rstrip("/")
    url = base_url + path
    headers = _build_headers(cfg, advertiser_id=advertiser_id, tenant=tenant)
    request_id = str(uuid.uuid4())

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=body,
            timeout=30.0,
        )

    try:
        body_data = response.json()
    except Exception:
        body_data = response.text

    return ApiResponse(
        status_code=response.status_code,
        body=body_data,
        request_id=request_id,
        curl=build_curl(
            method=method.upper(),
            url=str(response.request.url),
            headers=headers,
            body=body,
        ),
    )


def _headers_for_redirect(
    init_headers: dict[str, str],
    *,
    location: str,
    current_url: str,
    next_url: str,
) -> dict[str, str]:
    """Relative Location or same host → init headers; cross-host → drop Authorization."""
    parsed_location = urlparse(location)
    if not parsed_location.scheme and not parsed_location.netloc:
        return init_headers
    if urlparse(next_url).netloc.casefold() == urlparse(current_url).netloc.casefold():
        return init_headers
    return {k: v for k, v in init_headers.items() if k.lower() != "authorization"}


async def download_file(
    cfg: EnvConfig,
    url: str,
    params: dict[str, Any] | None = None,
    advertiser_id: int | None = None,
    tenant: str | None = None,
) -> DownloadResponse:
    """Download a file from an authenticated Walmart endpoint (e.g. display snapshot)."""
    init_headers = _build_headers(cfg, advertiser_id=advertiser_id, tenant=tenant)
    init_headers.pop("Content-Type", None)
    init_headers["Accept"] = "*/*"
    request_id = str(uuid.uuid4())

    hops: list[str] = []
    current_url = url
    request_params = params
    hop_headers = init_headers
    redirects_followed = 0

    async with httpx.AsyncClient(follow_redirects=False) as client:
        while True:
            response = await client.get(
                current_url,
                headers=hop_headers,
                params=request_params,
                timeout=120.0,
            )
            hops.append(str(response.request.url))
            request_params = None

            if response.status_code not in _REDIRECT_STATUS:
                break
            if redirects_followed >= _MAX_REDIRECTS:
                break

            location = response.headers.get("Location")
            if not location:
                break

            next_url = urljoin(str(response.url), location)
            hop_headers = _headers_for_redirect(
                init_headers,
                location=location,
                current_url=str(response.request.url),
                next_url=next_url,
            )
            current_url = next_url
            redirects_followed += 1

    return DownloadResponse(
        status_code=response.status_code,
        content=response.content,
        request_id=request_id,
        urls=",".join(hops),
    )
