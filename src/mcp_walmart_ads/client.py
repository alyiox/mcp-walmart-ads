"""HTTP execution against every platform this server fronts.

One request path serves both auth models; :func:`auth_headers` is the only place
they diverge. What each platform sends:

* **signature** (Walmart Connect, Sam's Club) -- the four ``WM_CONSUMER.*`` /
  ``WM_SEC.*`` signature headers, a long-lived ``Authorization: Bearer``, and the
  optional ``X-Advertiser-ID`` and ``wap-tenant-id`` an agent supplies. A 401 is
  terminal: nothing is cached, so a retry would send the same credential.
* **oauth2** (Marketplace) -- ``WM_SEC.ACCESS_TOKEN``, plus ``WM_MARKET`` and
  ``WM_GLOBAL_VERSION`` read from the operation's own declaration, and
  ``WM_SANDBOX`` when the target host is the sandbox. A 401 is retried once with
  a force-refreshed token, since Walmart can invalidate a token we still
  consider fresh.

On Marketplace the specs suggest a Basic ``Authorization`` header instead of, or
alongside, the access token -- 76 operations declare one, and two domains appear
Basic-only -- but that is documentation leakage from the ``/v3/token`` flow.
Probed live: Basic alone 401s, the access token alone succeeds. Sending a
long-lived client secret to every endpoint would be strictly worse, so it is
omitted. ``WM_SVC.NAME`` is likewise not readable from the specs (103 operations
declare the placeholder ``"Walmart Service Name"``), so it is fixed.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse, urlsplit

import httpx

from .auth import MARKETPLACE_SVC_NAME, AuthError, TokenManager, generate_signature
from .config import OAuth2Env, SignatureEnv
from .discovery import Operation
from .platforms import MARKETPLACE_SANDBOX_BASE_URL
from .specs import resolve_base_url

_MAX_REDIRECTS = 5
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
_PATH_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

DEFAULT_TIMEOUT = 60.0
DOWNLOAD_TIMEOUT = 120.0

JSON_MEDIA_TYPE = "application/json"

# WM_SANDBOX opts into Walmart's *dynamic* sandbox; the header's only legal value
# is "v2". It is required on every simulations-api operation and optional
# elsewhere, so it is sent whenever the target host is the sandbox.
SANDBOX_HEADER_VALUE = "v2"

DEFAULT_WM_MARKET = "US"
DEFAULT_WM_GLOBAL_VERSION = "3.1"

# Walmart spells the seller's Partner ID two ways: WM_PARTNER.ID on /v3/token
# (only for delegated grants) and WM_PARTNER_ID on the two payments operations
# that require it. Both are accepted here.
PARTNER_ID_HEADERS = ("WM_PARTNER_ID", "WM_PARTNER.ID")

EnvConfig = SignatureEnv | OAuth2Env


class RequestError(Exception):
    """Raised when a request cannot be built."""


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
    content_type: str | None


# ── request shaping ───────────────────────────────────────────────────────────


def resolve_path(path: str, path_params: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Substitute ``{placeholders}`` and split any query string baked into a path.

    One spec (``marketplace:walmart-plus``) keys a path as
    ``/v3/feeds?feedType=…&requestType=…``, so the query has to be lifted out
    before the URL is joined.
    """
    substituted = path
    if path_params:
        for key, value in path_params.items():
            substituted = substituted.replace("{" + key + "}", str(value))

    leftover = _PATH_PLACEHOLDER_RE.findall(substituted)
    if leftover:
        raise RequestError(
            f"path {path!r} still has unsubstituted placeholder(s): "
            f"{', '.join(leftover)} — pass them in path_params"
        )

    split = urlsplit(substituted)
    baked_params = dict(parse_qsl(split.query)) if split.query else {}
    return split.path, baked_params


def accept_for(operation: Operation | None, *, fallback: str) -> str:
    """Choose an ``Accept`` value from what the operation says it produces.

    Report and label endpoints negotiate strictly: they answer ``Accept: */*``
    with a 406 naming their acceptable representations, so the request has to
    name concrete types. JSON is preferred when offered, since that is what the
    rest of the tooling expects to parse.
    """
    declared = operation.response_media_types() if operation is not None else ()
    concrete = [m for m in declared if "*" not in m]
    if not concrete:
        return fallback
    if JSON_MEDIA_TYPE in concrete:
        return JSON_MEDIA_TYPE
    return ", ".join(concrete)


def requires_partner_id(operation: Operation | None) -> str | None:
    """Name of the partner-id header this operation requires, if any."""
    if operation is None:
        return None
    for param in operation.header_params():
        name = str(param.get("name", ""))
        if name.casefold() in {h.casefold() for h in PARTNER_ID_HEADERS} and param.get("required"):
            return name
    return None


async def auth_headers(
    cfg: EnvConfig,
    *,
    api: str,
    operation: Operation | None = None,
    tokens: TokenManager | None = None,
    advertiser_id: int | None = None,
    tenant: str | None = None,
    accept: str = JSON_MEDIA_TYPE,
    content_type: str | None = None,
    is_sandbox_host: bool = False,
    force_refresh: bool = False,
) -> dict[str, str]:
    """Assemble the full header set for one request, per the platform's auth model."""
    headers: dict[str, str] = {
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "Accept": accept,
    }
    if content_type is not None:
        headers["Content-Type"] = content_type

    if isinstance(cfg, SignatureEnv):
        sig = generate_signature(cfg.consumer_id, cfg.private_key_pem, cfg.private_key_version)
        headers.update(
            {
                "WM_CONSUMER.ID": cfg.consumer_id,
                "WM_CONSUMER.INTIMESTAMP": sig.timestamp,
                "WM_SEC.KEY_VERSION": sig.key_version,
                "WM_SEC.AUTH_SIGNATURE": sig.signature,
                "Authorization": f"Bearer {cfg.bearer_token}",
            }
        )
        if advertiser_id is not None:
            headers["X-Advertiser-ID"] = str(advertiser_id)
        if tenant:
            headers["wap-tenant-id"] = tenant
        return headers

    if tokens is None:
        raise AuthError(f"platform {cfg.platform!r} needs a token manager to authenticate")
    if advertiser_id is None:
        raise RequestError(f"platform {cfg.platform!r} requires an advertiser_id")

    credential = cfg.credential_for(advertiser_id)
    headers["WM_SVC.NAME"] = MARKETPLACE_SVC_NAME
    headers["WM_SEC.ACCESS_TOKEN"] = await tokens.access_token(
        credential,
        platform=cfg.platform,
        region=cfg.region,
        environment=cfg.environment,
        force_refresh=force_refresh,
    )

    if operation is None or operation.declares_header("WM_MARKET"):
        market = (
            operation.header_enum("WM_MARKET") if operation is not None else None
        ) or DEFAULT_WM_MARKET
        headers["WM_MARKET"] = market

    if operation is not None and operation.declares_header("WM_GLOBAL_VERSION"):
        headers["WM_GLOBAL_VERSION"] = (
            operation.header_enum("WM_GLOBAL_VERSION") or DEFAULT_WM_GLOBAL_VERSION
        )

    partner_id = cfg.partner_id_for(advertiser_id)
    if partner_id:
        for name in PARTNER_ID_HEADERS:
            if operation is None or operation.declares_header(name):
                headers[name] = partner_id
                break

    if is_sandbox_host or cfg.environment == "sandbox":
        headers["WM_SANDBOX"] = SANDBOX_HEADER_VALUE

    return headers


def redact(headers: dict[str, str]) -> dict[str, str]:
    """Replace credential material with placeholders for display.

    A cURL line is for shape, not for replay. The bearer token is long-lived and
    the signature is derived from the private key, so neither may reach a cached
    cURL resource; the access token is short-lived but redacted on the same
    principle.
    """
    out: dict[str, str] = {}
    for key, value in headers.items():
        folded = key.casefold()
        if folded == "authorization":
            out[key] = "Bearer $WM_BEARER_TOKEN" if value.startswith("Bearer ") else "$WM_AUTH"
        elif folded == "wm_sec.access_token":
            out[key] = "$WM_ACCESS_TOKEN"
        elif folded == "wm_sec.auth_signature":
            out[key] = "$WM_AUTH_SIGNATURE"
        else:
            out[key] = value
    return out


def build_curl(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any | None = None,
) -> str:
    parts = [f"curl -X {method.upper()} '{url}'"]
    for k, v in redact(headers).items():
        parts.append(f"  -H '{k}: {v}'")
    if body is not None:
        parts.append(f"  -d '{json.dumps(body)}'")
    return " \\\n".join(parts)


def _base_for(cfg: EnvConfig, api: str) -> str:
    config_base_urls = cfg.base_urls if isinstance(cfg, SignatureEnv) else None
    return resolve_base_url(api, cfg.environment, config_base_urls=config_base_urls)


def _decode(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


# ── execution ─────────────────────────────────────────────────────────────────


async def execute_request(
    *,
    cfg: EnvConfig,
    api: str,
    method: str,
    path: str,
    operation: Operation | None = None,
    params: dict[str, Any] | None = None,
    path_params: dict[str, Any] | None = None,
    body: dict[str, Any] | list[Any] | None = None,
    file_path: str | None = None,
    advertiser_id: int | None = None,
    tenant: str | None = None,
    tokens: TokenManager | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ApiResponse:
    """Execute one API call, retrying once with a fresh token after a 401.

    ``file_path`` switches the request to ``multipart/form-data`` with the file
    under the part name ``file``, which is how Marketplace feed uploads work and
    what every ``/v3/feeds`` schema requires.
    """
    required_partner_header = requires_partner_id(operation)
    if required_partner_header and isinstance(cfg, OAuth2Env):
        if advertiser_id is None or not cfg.partner_id_for(advertiser_id):
            target = operation.qualified_id if operation else path
            raise RequestError(
                f"{target} requires {required_partner_header}: "
                "add partner_id to this advertiser in the config"
            )

    resolved_path, baked_params = resolve_path(path, path_params)
    merged_params = {**baked_params, **(params or {})} or None
    root = _base_for(cfg, api).rstrip("/")
    url = root + resolved_path
    is_sandbox_host = root.startswith(MARKETPLACE_SANDBOX_BASE_URL)
    request_id = str(uuid.uuid4())

    files: dict[str, tuple[str, bytes, str]] | None = None
    if file_path is not None:
        source = Path(file_path).expanduser()
        try:
            payload = source.read_bytes()
        except OSError as e:
            raise RequestError(f"cannot read {source}: {e}") from e
        files = {"file": (source.name, payload, "application/octet-stream")}

    async def attempt(force_refresh: bool) -> tuple[httpx.Response, dict[str, str]]:
        headers = await auth_headers(
            cfg,
            api=api,
            operation=operation,
            tokens=tokens,
            advertiser_id=advertiser_id,
            tenant=tenant,
            accept=accept_for(operation, fallback=JSON_MEDIA_TYPE),
            content_type=(JSON_MEDIA_TYPE if body is not None and files is None else None),
            is_sandbox_host=is_sandbox_host,
            force_refresh=force_refresh,
        )
        if files is not None:
            # httpx sets the multipart Content-Type with its own boundary.
            headers.pop("Content-Type", None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=merged_params,
                json=body if files is None else None,
                files=files,
            )
        return response, headers

    response, headers = await attempt(force_refresh=False)
    if response.status_code == 401 and isinstance(cfg, OAuth2Env):
        response, headers = await attempt(force_refresh=True)

    return ApiResponse(
        status_code=response.status_code,
        body=_decode(response),
        request_id=request_id,
        curl=build_curl(method, str(response.request.url), headers, body),
    )


# ── download ──────────────────────────────────────────────────────────────────


def headers_for_redirect(
    init_headers: dict[str, str],
    *,
    location: str,
    current_url: str,
    next_url: str,
) -> dict[str, str]:
    """Relative Location or same host -> init headers; cross-host -> drop credentials.

    Report, label, and snapshot downloads redirect to signed storage URLs that
    reject Walmart auth headers outright, and forwarding a credential to a
    third-party host would leak it.
    """
    parsed_location = urlparse(location)
    if not parsed_location.scheme and not parsed_location.netloc:
        return init_headers
    if urlparse(next_url).netloc.casefold() == urlparse(current_url).netloc.casefold():
        return init_headers
    dropped = {"authorization", "wm_sec.access_token", "wm_sec.auth_signature"}
    return {k: v for k, v in init_headers.items() if k.casefold() not in dropped}


async def download(
    *,
    cfg: EnvConfig,
    api: str | None = None,
    url: str | None = None,
    method: str = "GET",
    path: str | None = None,
    operation: Operation | None = None,
    params: dict[str, Any] | None = None,
    path_params: dict[str, Any] | None = None,
    advertiser_id: int | None = None,
    tenant: str | None = None,
    tokens: TokenManager | None = None,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> DownloadResponse:
    """Fetch a binary payload, following redirects and shedding auth cross-host."""
    if url is None:
        if path is None or api is None:
            raise RequestError("provide url, or api with operation_id or method+path")
        resolved_path, baked_params = resolve_path(path, path_params)
        root = _base_for(cfg, api).rstrip("/")
        url = root + resolved_path
        params = {**baked_params, **(params or {})} or None

    init_headers = await auth_headers(
        cfg,
        api=api or "",
        operation=operation,
        tokens=tokens,
        advertiser_id=advertiser_id,
        tenant=tenant,
        accept=accept_for(operation, fallback="*/*"),
        is_sandbox_host=url.startswith(MARKETPLACE_SANDBOX_BASE_URL),
    )
    init_headers.pop("Content-Type", None)

    request_id = str(uuid.uuid4())
    current_url = url
    current_headers = init_headers
    hops = [url]
    request_params = params

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.request(
            method=method.upper(), url=current_url, headers=current_headers, params=request_params
        )
        for _ in range(_MAX_REDIRECTS):
            if response.status_code not in _REDIRECT_STATUS:
                break
            location = response.headers.get("location")
            if not location:
                break
            next_url = urljoin(current_url, location)
            current_headers = headers_for_redirect(
                current_headers,
                location=location,
                current_url=current_url,
                next_url=next_url,
            )
            current_url = next_url
            hops.append(current_url)
            # Query params belong to the original request; a signed redirect
            # target carries its own.
            response = await client.request(
                method=method.upper(), url=current_url, headers=current_headers
            )

    return DownloadResponse(
        status_code=response.status_code,
        content=response.content,
        request_id=request_id,
        urls=" → ".join(hops),
        content_type=response.headers.get("content-type"),
    )
