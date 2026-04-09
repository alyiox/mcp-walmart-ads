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
        "Read wmc://docs/* resources to learn endpoint schemas before calling the tool."
    ),
)

# ── resources ──────────────────────────────────────────────────────────────────


@mcp.resource("wmc://docs/{ad_type}/{endpoint_group}")
def doc_resource(ad_type: str, endpoint_group: str) -> str:
    """[WalmartAds] API reference doc. Src: docs."""
    uri = f"wmc://docs/{ad_type}/{endpoint_group}"
    content = read_doc_resource(uri)
    if content is None:
        return f"No documentation found for {uri}"
    return content


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
    body: dict[str, Any] | None = None,
) -> str:
    """[WalmartAds] Execute authenticated Walmart Connect Ads API request.

    Args:
        region: API region, e.g. US. Src: regions.
        env: Target environment — production or sandbox. Src: environments.
        ad_type: API family — search or display. Src: ad_types.
        method: HTTP method — GET, POST, PUT, or DELETE.
        path: API path after base URL, e.g. /api/v1/campaigns.
        params: Query string parameters as a JSON object.
        body: JSON request body for POST/PUT.
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
    # Register all bundled doc resources so list_resources works
    for doc in list_doc_resources():
        pass  # FastMCP discovers them via the @mcp.resource decorator pattern above
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
