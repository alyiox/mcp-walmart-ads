from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import generate_signature
from .config import EnvConfig


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


def _build_headers(cfg: EnvConfig) -> dict[str, str]:
    sig = generate_signature(cfg.consumer_id, cfg.private_key_pem, cfg.private_key_version)
    return {
        "WM_CONSUMER.ID": cfg.consumer_id,
        "WM_CONSUMER.INTIMESTAMP": sig.timestamp,
        "WM_SEC.KEY_VERSION": sig.key_version,
        "WM_SEC.AUTH_SIGNATURE": sig.signature,
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "Authorization": f"Bearer {cfg.bearer_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


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
) -> ApiResponse:
    base_url = cfg.base_urls[ad_type].rstrip("/")
    url = base_url + path
    headers = _build_headers(cfg)
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


async def download_file(
    cfg: EnvConfig,
    url: str,
    params: dict[str, Any] | None = None,
) -> DownloadResponse:
    """Download a file from an authenticated Walmart endpoint (e.g. display snapshot)."""
    headers = _build_headers(cfg)
    headers.pop("Content-Type", None)
    headers["Accept"] = "*/*"
    request_id = str(uuid.uuid4())

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params, timeout=120.0)

    return DownloadResponse(
        status_code=response.status_code,
        content=response.content,
        request_id=request_id,
    )
