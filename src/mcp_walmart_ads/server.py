from __future__ import annotations

import gzip
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, model_serializer

from .client import download_file, execute_request
from .config import load_config
from .resources import ResponseCache, list_doc_resources, read_cached_response, read_doc_resource

config = load_config()
cache = ResponseCache(ttl_seconds=config.response_cache_ttl)

mcp = FastMCP(
    "Walmart Connect Ads",
    instructions=(
        "MCP server for Walmart Connect Ads APIs. "
        "Use the walmart_ads_api tool to execute API calls. "
        "The tool description includes an endpoint index with methods and paths. "
        "For request/response field details, read the doc resources: "
        "wmc://docs/search/campaigns, wmc://docs/search/ad-groups, "
        "wmc://docs/search/ad-items, wmc://docs/search/keywords, "
        "wmc://docs/search/placements, wmc://docs/search/bid-multipliers, "
        "wmc://docs/search/sponsored-brands, wmc://docs/search/sponsored-videos, "
        "wmc://docs/search/catalog-item-search, wmc://docs/search/snapshot-reports, "
        "wmc://docs/search/top-search-trends, wmc://docs/search/advanced-insights, "
        "wmc://docs/search/stats, wmc://docs/search/audit-snapshot, "
        "wmc://docs/display/campaigns, wmc://docs/display/ad-groups, "
        "wmc://docs/display/targeting, wmc://docs/display/audiences, "
        "wmc://docs/display/itemsets, wmc://docs/display/itemset-campaign-association, "
        "wmc://docs/display/catalog, wmc://docs/display/forecast, "
        "wmc://docs/display/creative, wmc://docs/display/creative-associations, "
        "wmc://docs/display/video, wmc://docs/display/folder, "
        "wmc://docs/display/snapshot-reports, wmc://docs/display/stats, "
        "wmc://docs/display/brand-landing-page."
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


def _register_doc_resources() -> None:
    """Register each bundled doc as a static resource (not a template)."""

    def _make_handler(uri: str):  # noqa: ANN202 – closure factory
        def handler() -> str:
            content = read_doc_resource(uri)
            return content or f"No documentation found for {uri}"

        return handler

    for doc in list_doc_resources():
        mcp.resource(
            doc["uri"],
            name=doc["name"],
            description=doc["description"],
            mime_type=doc["mime_type"],
        )(_make_handler(doc["uri"]))


_register_doc_resources()


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
async def walmart_ads_api(
    region: str,
    env: str,
    ad_type: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | list[Any] | None = None,
) -> ApiToolResult:
    r"""[WalmartAds] Execute authenticated Walmart Connect Ads API request.

    Args:
        region: API region, e.g. US. Src: config.
        env: Target environment — production or staging. Src: config.
        ad_type: API family — search or display. Src: config.
        method: HTTP method — GET, POST, PUT, or DELETE.
        path: API path after base URL, e.g. /api/v1/campaigns.
        params: Query string parameters as a JSON object.
        body: JSON request body for POST/PUT (object or array when the API requires it).

    Endpoint index (read wmc://docs/{ad_type}/{group} for field details):

    search — Sponsored Search (Sponsored Products, SBA, Video)
      GET    /api/v1/campaigns          list campaigns
      POST   /api/v1/campaigns          create campaigns (array body)
      PUT    /api/v1/campaigns          update campaigns (array body)
      PUT    /api/v1/campaigns/delete   delete campaigns (array body)
      GET    /api/v1/adGroups           list ad groups
      POST   /api/v1/adGroups           create ad groups (array body)
      PUT    /api/v1/adGroups           update ad groups (array body)
      PUT    /api/v1/adGroups/delete    delete ad groups (array body)
      GET    /api/v1/keywords           list keywords
      POST   /api/v1/keywords           create keywords (array body)
      PUT    /api/v1/keywords           update keywords (array body)
      PUT    /api/v1/keywords/delete    delete keywords (array body)
      POST   /api/v2/snapshot/report              request performance report snapshot
      GET    /api/v2/snapshot                    retrieve performance report snapshot
      POST   /api/v1/snapshot/entity             request entity snapshot
      GET    /api/v1/snapshot                    retrieve entity snapshot
      POST   /api/v1/snapshot/insight            request insight snapshot
      POST   /api/v1/snapshot/recommendations    request item/keyword recommendations
      POST   /api/v2/snapshot/recommendations    request campaign recommendations

    display — Display Advertising
      GET    /api/v1/campaignGroups     list campaign groups
      POST   /api/v1/campaignGroups     create campaign group
      PUT    /api/v1/campaignGroups     update campaign group
      GET    /api/v1/lineItems          list line items
      POST   /api/v1/lineItems          create line item
      PUT    /api/v1/lineItems          update line item
      POST   /api/v2/targeting/list      list contextual/behavioral targets
      POST   /api/v1/geoLocations/list  list geo location targets
      POST   /api/v1/audiences          create custom audience
      PATCH  /api/v1/audiences          update custom audience
      POST   /api/v1/audiences/list     list custom audiences
      POST   /api/v1/audiences/brand    create brand audience
      GET    /api/v1/audiences/brand/status  get brand audience status
      POST   /api/v1/audiences/estimate      audience size estimate
      POST   /api/v1/audiences/intelligence  audience intelligence
      POST   /api/v1/itemset            create itemset
      POST   /api/v1/itemsets/list      list itemsets
      PUT    /api/v1/itemset            update itemset
      POST   /api/v1/itemset/info       get itemset info
      POST   /api/v1/itemset/expression get itemset expression
      POST   /api/v1/snapshot/report    request snapshot report
      GET    /api/v1/snapshot           retrieve snapshot (report or entity)
      POST   /api/v1/snapshot/entity    request entity snapshot

    Display snapshot files require authenticated download — use
    walmart_ads_download_display_snapshot with the URL from the `details` field.
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
async def walmart_ads_download_display_snapshot(
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


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
