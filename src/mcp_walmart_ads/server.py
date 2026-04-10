from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import execute_request
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
        "wmc://docs/search/keywords, wmc://docs/search/snapshot-reports, "
        "wmc://docs/display/campaigns, wmc://docs/display/snapshot-reports."
    ),
)

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


@mcp.resource("wmc://responses/{request_id}")
def cached_response_resource(request_id: str) -> str:
    """[WalmartAds] Retrieve full cached API response. Src: responses."""
    content = read_cached_response(request_id, cache)
    if content is None:
        return f"No cached response found for request_id={request_id} (may have expired)."
    return content


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
) -> str:
    r"""[WalmartAds] Execute authenticated Walmart Connect Ads API request.

    Args:
        region: API region, e.g. US. Src: regions.
        env: Target environment — production or sandbox. Src: environments.
        ad_type: API family — search or display. Src: ad_types.
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
      POST   /api/v1/snapshot/report    request snapshot report
      GET    /api/v1/snapshot           retrieve snapshot (report or entity)
      POST   /api/v1/snapshot/entity    request entity snapshot
    """
    region_upper = region.upper()
    env_lower = env.lower()

    if region_upper not in config.regions:
        available = ", ".join(config.regions.keys())
        return f"Error: region '{region}' not found in config. Available: {available}"

    if env_lower not in config.regions[region_upper]:
        available = ", ".join(config.regions[region_upper].keys())
        return f"Error: env '{env}' not found for region '{region}'. Available: {available}"

    ad_type_lower = ad_type.lower()
    if ad_type_lower not in ("search", "display"):
        return "Error: ad_type must be 'search' or 'display'."

    env_cfg = config.regions[region_upper][env_lower]

    if ad_type_lower not in env_cfg.base_urls:
        return f"Error: base_url for ad_type '{ad_type}' not configured for {region}/{env}."

    response = await execute_request(
        cfg=env_cfg,
        ad_type=ad_type_lower,
        method=method,
        path=path,
        params=params,
        body=body,
    )

    body_str = (
        json.dumps(response.body, indent=2) if not isinstance(response.body, str) else response.body
    )
    body_bytes = body_str.encode()

    if len(body_bytes) > config.truncate_threshold:
        cache.put(response.request_id, response.body)
        preview = body_str[: config.truncate_threshold].rsplit("\n", 1)[0]
        return (
            f"HTTP {response.status_code}\n"
            f"[Response truncated: {len(body_bytes):,} bytes "
            f"> {config.truncate_threshold:,} byte threshold]\n"
            f"Full response cached at: wmc://responses/{response.request_id}\n\n"
            f"{preview}\n... (truncated)"
        )

    return f"HTTP {response.status_code}\n\n{body_str}"


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
