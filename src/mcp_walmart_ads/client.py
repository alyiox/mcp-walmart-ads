from __future__ import annotations

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


async def execute_request(
    cfg: EnvConfig,
    ad_type: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
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
    )
