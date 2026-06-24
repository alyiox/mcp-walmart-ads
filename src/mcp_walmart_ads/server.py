from __future__ import annotations

import gzip
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, model_serializer

from . import discovery, specs
from .client import download_file, execute_request
from .config import load_config
from .resources import ResponseCache, read_cached_response
from .specs import SpecError

config = load_config()
cache = ResponseCache(ttl_seconds=config.response_cache_ttl)

mcp = FastMCP(
    "Walmart Connect Ads",
    instructions=(
        "MCP server for Walmart Connect Ads APIs. "
        "Discover endpoints with list_endpoints (filter by query/tag/method) "
        "and inspect one with describe_endpoint (returns the operation plus "
        "its schema closure). Execute with call_endpoint — by operation_id, or by raw "
        "method+path (raw path also reaches alpha/beta/unpublished endpoints not in the "
        "specs). The specs are bundled and can be refreshed at runtime from the public "
        "registry with refresh_specs."
    ),
)

# ── tool result models ─────────────────────────────────────────────────────────


class _ExcludeNone(BaseModel):
    @model_serializer(mode="wrap")
    def _exclude_none(self, handler: Any) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


class ApiToolResult(_ExcludeNone):
    status_code: int | None = None
    body: Any | None = None
    truncated: bool | None = None
    cached_at: str | None = None  # wmc://responses/{request_id}
    curl: str | None = None  # wmc://curl/{request_id}
    error: str | None = None


class DownloadToolResult(_ExcludeNone):
    status_code: int | None = None
    size_bytes: int | None = None
    cached_at: str | None = None  # wmc://responses/{request_id}
    error: str | None = None


# ── resources ──────────────────────────────────────────────────────────────────


@mcp.resource("wmc://config")
def get_config() -> str:
    """[WalmartAds] Available regions, environments, and ad types. Src: config."""
    result: dict[str, Any] = {}
    for region, envs in config.regions.items():
        result[region] = {}
        for env_name, env_cfg in envs.items():
            result[region][env_name] = list(env_cfg.base_urls.keys())
    return json.dumps({"regions": result}, indent=2)


@mcp.resource("wmc://responses/{request_id}")
def cached_response_resource(request_id: str) -> str:
    """[WalmartAds] Retrieve full cached API response. Src: responses."""
    content = read_cached_response(request_id, cache)
    if content is None:
        return f"No cached response found for request_id={request_id} (may have expired)."
    return content


@mcp.resource("wmc://curl/{request_id}")
def cached_curl_resource(request_id: str) -> str:
    """[WalmartAds] Retrieve cURL command for a previous API request."""
    data = cache.get(f"curl/{request_id}")
    if data is None:
        return f"No cURL command found for request_id={request_id} (may have expired)."
    return f"# cURL (auth headers are time-limited)\n\n{data}"


# ── tool ───────────────────────────────────────────────────────────────────────


@mcp.tool()
async def call_endpoint(
    region: str,
    env: str,
    ad_type: str,
    method: str | None = None,
    path: str | None = None,
    operation_id: str | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | list[Any] | None = None,
) -> ApiToolResult:
    r"""[WalmartAds] Execute authenticated Walmart Connect Ads API request.

    Specify the endpoint either by ``operation_id`` (discovered via
    list_endpoints / describe_endpoint) or by raw
    ``method`` + ``path``. Raw method+path also reaches alpha/beta/unpublished
    endpoints that are not in the bundled specs.

    Args:
        region: API region, e.g. US. Src: config.
        env: Target environment — production or staging. Src: config.
        ad_type: API family — search or display. Src: config.
        method: HTTP method — GET, POST, PUT, PATCH, or DELETE. Required unless
            operation_id is given.
        path: API path after base URL, e.g. /api/v1/campaigns. Required unless
            operation_id is given.
        operation_id: Spec operation id (e.g. AdGroupList). Resolves method+path
            from the ad_type spec. Src: operations.
        params: Query string parameters as a JSON object.
        body: JSON request body for POST/PUT (object or array when the API requires it).

    Display snapshot files require authenticated download — use
    download_display_snapshot with the URL from the `details` field.
    """
    region_upper = region.upper()
    env_lower = env.lower()

    if region_upper not in config.regions:
        available = ", ".join(config.regions.keys())
        msg = f"region '{region}' not found in config. Available: {available}"
        return ApiToolResult(error=msg)

    if env_lower not in config.regions[region_upper]:
        available = ", ".join(config.regions[region_upper].keys())
        msg = f"env '{env}' not found for region '{region}'. Available: {available}"
        return ApiToolResult(error=msg)

    ad_type_lower = ad_type.lower()
    if ad_type_lower not in ("search", "display"):
        return ApiToolResult(error="ad_type must be 'search' or 'display'.")

    if operation_id is not None:
        try:
            op = discovery.get_operation(ad_type_lower, operation_id)
        except SpecError as e:
            return ApiToolResult(error=str(e))
        method, path = op.method, op.path
    if not method or not path:
        return ApiToolResult(error="provide operation_id, or both method and path.")

    env_cfg = config.regions[region_upper][env_lower]

    if ad_type_lower not in env_cfg.base_urls:
        msg = f"base_url for ad_type '{ad_type}' not configured for {region}/{env}."
        return ApiToolResult(error=msg)

    response = await execute_request(
        cfg=env_cfg,
        ad_type=ad_type_lower,
        method=method,
        path=path,
        params=params,
        body=body,
    )

    cache.put(f"curl/{response.request_id}", response.curl)
    curl_ref = f"wmc://curl/{response.request_id}"

    body_str = (
        json.dumps(response.body, indent=2) if not isinstance(response.body, str) else response.body
    )
    body_bytes = body_str.encode()

    if len(body_bytes) > config.truncate_threshold:
        cache.put(response.request_id, response.body)
        preview = body_str[: config.truncate_threshold].rsplit("\n", 1)[0] + "\n... (truncated)"
        return ApiToolResult(
            status_code=response.status_code,
            body=preview,
            truncated=True,
            cached_at=f"wmc://responses/{response.request_id}",
            curl=curl_ref,
        )

    return ApiToolResult(
        status_code=response.status_code,
        body=response.body,
        curl=curl_ref,
    )


_DISPLAY_SNAPSHOT_URL = "https://advertising.walmart.com/display/file/{snapshot_id}"


@mcp.tool()
async def download_display_snapshot(
    region: str,
    env: str,
    snapshot_id: str,
    advertiser_id: int,
) -> DownloadToolResult:
    r"""[WalmartAds] Download a display snapshot file (report or entity).

    Display snapshot download URLs require authenticated requests with Walmart
    API headers. Use this tool with the URL from the ``details`` field after
    polling a display snapshot to ``done`` status.

    Args:
        region: API region, e.g. US. Src: config.
        env: Target environment — production or staging. Src: config.
        snapshot_id: The snapshot ID from the ``details`` URL (e.g. ``1a``).
        advertiser_id: The advertiser ID used when creating the snapshot.
    """
    region_upper = region.upper()
    env_lower = env.lower()

    if region_upper not in config.regions:
        available = ", ".join(config.regions.keys())
        msg = f"region '{region}' not found in config. Available: {available}"
        return DownloadToolResult(error=msg)

    if env_lower not in config.regions[region_upper]:
        available = ", ".join(config.regions[region_upper].keys())
        msg = f"env '{env}' not found for region '{region}'. Available: {available}"
        return DownloadToolResult(error=msg)

    env_cfg = config.regions[region_upper][env_lower]
    url = _DISPLAY_SNAPSHOT_URL.format(snapshot_id=snapshot_id)

    response = await download_file(cfg=env_cfg, url=url, params={"advertiserId": advertiser_id})

    if response.status_code != 200:
        return DownloadToolResult(status_code=response.status_code, error="Download failed.")

    try:
        text = gzip.decompress(response.content).decode()
    except gzip.BadGzipFile:
        text = response.content.decode()

    cache.put(response.request_id, text)
    return DownloadToolResult(
        status_code=response.status_code,
        size_bytes=len(text.encode()),
        cached_at=f"wmc://responses/{response.request_id}",
    )


# ── discovery + refresh tools ────────────────────────────────────────────────


@mcp.tool()
async def list_endpoints(
    ad_type: str,
    query: str | None = None,
    tag: str | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    r"""[WalmartAds] List OpenAPI operations for an ad_type with optional filters.

    Args:
        ad_type: API family — search or display. Src: config.
        query: Case-insensitive substring match on operationId, path, or summary.
        tag: Filter to operations whose OpenAPI tags include this value.
        method: Filter by HTTP verb — GET, POST, PUT, PATCH, or DELETE.
    """
    try:
        endpoints = discovery.list_endpoints(ad_type.lower(), query=query, tag=tag, method=method)
    except SpecError as e:
        return {"error": str(e)}
    return {"ad_type": ad_type.lower(), "count": len(endpoints), "endpoints": endpoints}


@mcp.tool()
async def describe_endpoint(ad_type: str, operation_id: str) -> dict[str, Any]:
    r"""[WalmartAds] Describe one OpenAPI operation with its schema closure.

    Returns the operation plus every ``components.schemas`` entry reachable from
    it, so request bodies and responses can be built without the full spec.

    Args:
        ad_type: API family — search or display. Src: config.
        operation_id: Spec operation id. Src: operations.
    """
    try:
        return discovery.describe_endpoint(ad_type.lower(), operation_id)
    except SpecError as e:
        return {"error": str(e)}


@mcp.tool()
async def refresh_specs(spec_id: str | None = None) -> dict[str, Any]:
    r"""[WalmartAds] Refresh bundled OpenAPI specs from ReadMe's public registry.

    Re-fetches the latest spec JSON into a user cache that takes precedence over
    the bundled copy. Omit spec_id to refresh all specs.

    Args:
        spec_id: One of search/sponsored-products, display/display-rest-api,
            display/ad-id-token-generation, display/conversion-rest-api. Src: specs.
    """
    try:
        results = await specs.refresh(spec_id)
    except SpecError as e:
        return {"error": str(e)}
    return {"refreshed": results}


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
