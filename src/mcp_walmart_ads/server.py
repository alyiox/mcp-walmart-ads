"""MCP server exposing Walmart Connect, Sam's Club, and Walmart Marketplace APIs.

Five tools over one hierarchical ``api`` namespace -- ``<retailer>:<line>:<name>``,
as in ``walmart:ads:sponsored-products``, ``samsclub:ads:sponsored-products``,
``walmart:marketplace:order-management``. Credentials attach at the two-segment
prefix, so an operation id resolves to a platform, a base URL, and an auth model
without the caller naming any of them; ``api`` is only required when calling by
raw method+path, where there is no operation to infer it from.

Two parameters carry that namespace, and only two. ``api`` is an exact id on every
tool, and ``platform`` is the coarse filter on ``list_endpoints``. The segments
have names -- retailer, line -- but neither is a parameter, because neither is
independently meaningful.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, model_serializer

from . import client, discovery, specs
from .auth import AuthError, TokenManager
from .client import RequestError
from .config import Config, ConfigError, EnvConfig, OAuth2Env, SignatureEnv, load_config
from .platforms import OAUTH2, PLATFORM_IDS, UnknownPlatform, platform_for, platform_of
from .resources import ResponseCache, read_cached_response
from .specs import SpecError

mcp = MCPServer(
    "Walmart APIs",
    instructions=(
        "MCP server for Walmart Connect Ads, Sam's Club Sponsored Ads, and Walmart "
        "Marketplace APIs. Api ids are hierarchical — <retailer>:<line>:<name>, e.g. "
        "walmart:ads:sponsored-products, samsclub:ads:sponsored-products, "
        "walmart:marketplace:order-management — and an operation id appends "
        ":operationId. Credentials attach at the two-segment prefix, so an operation id "
        "alone determines which platform, host, and auth model a call uses. Discover "
        "endpoints with list_endpoints (filter by query/api/platform/tag/method) and "
        "inspect one with describe_endpoint, which returns the operation plus its schema "
        "closure, minus the headers the server supplies itself. Execute "
        "with call_endpoint — by operation_id, or by raw method+path with an api. "
        "walmart:marketplace calls need an advertiser_id, which selects the credential; "
        "on the ads platforms it is an optional header. Discovery starts at "
        "wmt://platforms — what is configured and callable — and descends: "
        "/{platform}/apis for api ids, /{platform}/apis/{name} for one api's tags, "
        "/{platform}/regions/{region}/{environment}/advertisers or /hosts for what that "
        "environment carries. Fetch reports, labels, and snapshots with download_file. "
        "The 33 bundled specs can be refreshed at runtime with refresh_specs."
    ),
)

# Declared as Literals so the host rejects a bad value before the call is made,
# rather than the server returning an error string a round trip later. Both sets
# are closed and small; ``api`` is deliberately not enumerated -- 31 values on
# four tools would cost ~1,270 tokens to duplicate what wmt://platforms/*/apis lists.
# tests/test_server.py asserts these stay in step with their sources.
PlatformId = Literal["walmart:ads", "walmart:marketplace", "samsclub:ads"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]

# Above this, describe_endpoint hands back the operation without its response
# schemas and parks the whole payload at wmt://responses/{operation_id}. It is
# not truncate_threshold: that is 1 KB by default, below the median describe.
DESCRIBE_THRESHOLD = 20 * 1024

tokens = TokenManager()

_config: Config | None = None
_cache: ResponseCache | None = None


def config() -> Config:
    """Load and memoize the config.

    Deliberately lazy: discovery over the bundled specs must work on a machine
    with no credentials at all, so a missing config file only fails the tools
    that actually need it.
    """
    global _config, _cache
    if _config is None:
        _config = load_config()
        _cache = ResponseCache(ttl_seconds=_config.response_cache_ttl)
    return _config


def cache() -> ResponseCache:
    """The response cache, which does not depend on a config being present.

    ``config()`` builds it with the configured TTL; on a machine with no config
    file the discovery tools still cache, on the default TTL, because nothing
    they park there is credential-derived.
    """
    global _cache
    if _cache is None:
        try:
            config()
        except ConfigError:
            _cache = ResponseCache()
    assert _cache is not None
    return _cache


class _ExcludeNone(BaseModel):
    @model_serializer(mode="wrap")
    def _exclude_none(self, handler: Any) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


class ApiToolResult(_ExcludeNone):
    status_code: int | None = None
    body: Any | None = None
    truncated: bool | None = None
    cached_at: str | None = None  # wmt://responses/{request_id}
    curl: str | None = None  # wmt://curl/{request_id}
    error: str | None = None


class DownloadToolResult(_ExcludeNone):
    status_code: int | None = None
    path: str | None = None
    bytes_written: int | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    cached_at: str | None = None  # wmt://responses/{request_id}
    urls: str | None = None  # hop URLs (start → … → last)
    error: str | None = None


# ── resources ──────────────────────────────────────────────────────────────────


def _config_or_raise() -> Config:
    """The loaded config, or a resource error carrying the loader's message.

    A read that cannot be answered fails on the wire rather than returning an
    error document: the SDK maps this to a JSON-RPC error with the uri attached,
    and the message already says what to fix and that a fix needs a restart.
    """
    try:
        return config()
    except ConfigError as e:
        raise ResourceError(str(e)) from e


def _env_or_raise(platform: str, region: str, environment: str) -> EnvConfig:
    try:
        return _config_or_raise().env(platform, region, environment)
    except ConfigError as e:
        raise ResourceNotFoundError(str(e)) from e


@mcp.resource(
    "wmt://platforms",
    name="platforms",
    mime_type="application/json",
    description=(
        "[Walmart] List every platform, its auth model, and the regions and environments "
        "it declares. A platform with no regions cannot be called — read one of its "
        "sub-resources to be told why. oauth2 platforms require an advertiser_id; "
        "signature platforms do not. Src: platforms."
    ),
)
def get_platforms() -> str:
    """Topology only: what exists, and where a call can be aimed.

    Nothing here is derived from the specs, so a refresh cannot move it and it
    renders on a machine with no spec files. Nothing here diagnoses either --
    a platform that failed to load simply has no regions, and asking for one of
    its environments raises the loader's own message.
    """
    cfg = _config_or_raise()
    out: dict[str, Any] = {}
    for platform in PLATFORM_IDS:
        entry: dict[str, Any] = {
            "auth": "oauth2" if platform_for(platform).auth is OAUTH2 else "signature"
        }
        regions = cfg.platforms.get(platform)
        if regions is not None and platform not in cfg.platform_errors:
            entry["regions"] = {region: sorted(envs) for region, envs in regions.items()}
        out[platform] = entry
    return json.dumps(out, indent=2)


@mcp.resource(
    "wmt://platforms/{platform}/apis",
    name="apis",
    mime_type="application/json",
    description=(
        "[Walmart] List one platform's api ids, ready to pass as api. Two apis whose "
        "<line>:<name> suffix matches cover the same surface for different retailers, "
        "but overlap only partly — an operation on one may not exist on the other. "
        "Src: specs."
    ),
)
def get_apis(platform: str) -> str:
    try:
        return json.dumps(discovery.apis_for(platform), indent=2)
    except UnknownPlatform as e:
        raise ResourceNotFoundError(str(e)) from e


@mcp.resource(
    "wmt://platforms/{platform}/apis/{name}",
    name="api",
    mime_type="application/json",
    description=(
        "[Walmart] Describe one api: title, version, operation count, and its tags with "
        "the number of operations under each — the legal values for list_endpoints(tag). "
        "only appears when the api serves a single environment. Src: specs."
    ),
)
def get_api(platform: str, name: str) -> str:
    """``name`` is the api's last segment, or the whole id, whichever a caller has."""
    api = name if name.startswith(f"{platform}:") else f"{platform}:{name}"
    try:
        return json.dumps(discovery.api_detail(api), indent=2)
    except SpecError as e:
        raise ResourceNotFoundError(str(e)) from e


@mcp.resource(
    "wmt://platforms/{platform}/regions/{region}/{environment}/advertisers",
    name="advertisers",
    mime_type="application/json",
    description=(
        "[Walmart] List one environment's advertiser ids, each mapped to its Walmart "
        "Partner ID or null. An id selects the credential a walmart:marketplace call "
        "acts as. Src: platforms."
    ),
)
def get_advertisers(platform: str, region: str, environment: str) -> str:
    cfg = _env_or_raise(platform, region, environment)
    if not isinstance(cfg, OAuth2Env):
        raise ResourceNotFoundError(
            f"{platform} authenticates by signature and has no advertisers; "
            f"read wmt://platforms/{platform}/regions/{region}/{environment}/hosts"
        )
    return json.dumps(
        {str(a): cfg.partner_id_for(a) for a in cfg.advertisers},
        indent=2,
    )


@mcp.resource(
    "wmt://platforms/{platform}/regions/{region}/{environment}/hosts",
    name="hosts",
    mime_type="application/json",
    description=(
        "[Walmart] List one environment's api ids mapped to the base URL a call reaches. "
        "Walmart issues these per tenant, so they come from config rather than the specs. "
        "Src: platforms."
    ),
)
def get_hosts(platform: str, region: str, environment: str) -> str:
    cfg = _env_or_raise(platform, region, environment)
    if not isinstance(cfg, SignatureEnv):
        raise ResourceNotFoundError(
            f"{platform} base URLs are fixed by the server, not configured; "
            f"read wmt://platforms/{platform}/regions/{region}/{environment}/advertisers"
        )
    return json.dumps(cfg.base_urls, indent=2)


@mcp.resource(
    "wmt://responses/{request_id}",
    name="cached_response",
    description="[Walmart] Retrieve full cached API response. Src: responses.",
)
def get_cached_response(request_id: str) -> str:
    content = read_cached_response(request_id, cache())
    if content is None:
        raise ResourceNotFoundError(
            f"no cached response for request_id={request_id} (it may have expired)"
        )
    return content


@mcp.resource(
    "wmt://curl/{request_id}",
    name="cached_curl",
    description=(
        "[Walmart] Retrieve cURL command for a previous API request. "
        "Credentials are replaced with placeholders. Src: responses."
    ),
)
def get_cached_curl(request_id: str) -> str:
    data = cache().get(f"curl/{request_id}")
    if data is None:
        raise ResourceNotFoundError(f"no cURL for request_id={request_id} (it may have expired)")
    return f"# cURL (credentials replaced with placeholders)\n\n{data}"


# ── discovery tools ────────────────────────────────────────────────────────────


@mcp.tool(
    name="list_endpoints",
    description=(
        "[Walmart] List OpenAPI operations across every api. Returned operation ids can be "
        "passed straight to describe_endpoint or call_endpoint."
    ),
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
async def list_endpoints(
    query: Annotated[
        str | None,
        Field(
            default=None,
            description=("Case-insensitive substring match on operation id, path, or summary."),
        ),
    ] = None,
    api: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Limit to one api, e.g. walmart:marketplace:order-management. "
                "A platform prefix is not accepted here — use platform for that. Src: platforms."
            ),
        ),
    ] = None,
    platform: Annotated[
        PlatformId | None,
        Field(
            default=None,
            description="Limit to one platform. Src: platforms.",
        ),
    ] = None,
    tag: Annotated[
        str | None,
        Field(
            default=None,
            description="Filter to operations whose OpenAPI tags include this value.",
        ),
    ] = None,
    method: Annotated[
        HttpMethod | None,
        Field(default=None, description="Filter by HTTP verb."),
    ] = None,
    limit: Annotated[
        int,
        Field(
            default=50,
            ge=1,
            le=500,
            description="Rows to return from offset. The largest single api has 87.",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Field(default=0, ge=0, description="Rows to skip. Pass next_offset from a prior call."),
    ] = 0,
) -> dict[str, Any]:
    if query is None and api is None and platform is None and tag is None and method is None:
        # All 424 rows are 130 KB, and an unfiltered call is what a caller makes
        # before it knows how to narrow. Say where the operations are instead.
        counts = discovery.count_by_api()
        return {
            "count": sum(counts.values()),
            "by_api": counts,
            "hint": "narrow with api, platform, query, tag or method",
        }
    try:
        endpoints = discovery.list_endpoints(
            query=query, api=api, platform=platform, tag=tag, method=method
        )
    except (SpecError, UnknownPlatform) as e:
        return {"error": str(e)}
    page = endpoints[offset : offset + limit]
    result: dict[str, Any] = {
        "count": len(endpoints),
        "returned": len(page),
        "endpoints": page,
    }
    if offset + len(page) < len(endpoints):
        result["next_offset"] = offset + len(page)
    return result


@mcp.tool(
    name="describe_endpoint",
    description=(
        "[Walmart] Describe one OpenAPI operation. Returns it with every components.schemas "
        "entry reachable from it, so a request body can be built without the full spec."
    ),
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
async def describe_endpoint(
    operation_id: Annotated[
        str,
        Field(
            description=(
                "Operation id, qualified as api:operationId (e.g. "
                "walmart:marketplace:order-management:getAllOrders) or bare when "
                "unambiguous. Src: operations."
            )
        ),
    ],
    api: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Api to resolve a bare operation_id in, e.g. "
                "walmart:ads:sponsored-products. Src: platforms."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    try:
        described = discovery.describe_endpoint(operation_id, api=api)
    except SpecError as e:
        return {"error": str(e)}

    if len(json.dumps(described).encode()) <= DESCRIBE_THRESHOLD:
        return described

    # Response schemas are the bulk -- 66 KB of the largest 90 KB operation --
    # and the part a caller does not need in order to build a request, so they
    # are deferred whole rather than truncated mid-structure.
    request_id = described["operation_id"]
    cache().put(request_id, described)
    operation = {k: v for k, v in described["operation"].items() if k != "responses"}
    return {
        **described,
        "operation": operation,
        "truncated": True,
        "cached_at": f"wmt://responses/{request_id}",
    }


# ── execution tools ────────────────────────────────────────────────────────────


def _resolve_target(
    operation_id: str | None,
    api: str | None,
    method: str | None,
    path: str | None,
) -> tuple[discovery.Operation | None, str, str, str]:
    """Resolve (operation, api, method, path), raising SpecError or RequestError."""
    if operation_id is not None:
        operation = discovery.get_operation(operation_id, api=api)
        return operation, operation.api, operation.method, operation.path
    if not api:
        raise RequestError(
            "provide operation_id, or api together with method and path "
            "(api is one of the ids in wmt://platforms/<platform>/apis; "
            f"platforms: {', '.join(PLATFORM_IDS)})"
        )
    if not method or not path:
        raise RequestError("provide operation_id, or both method and path.")
    specs.meta_for(api)  # raises SpecError on an unknown api
    return None, api, method, path


@mcp.tool(
    name="call_endpoint",
    description=(
        "[Walmart] Execute an authenticated API request. Identify the endpoint by operation_id, "
        "or by method + path with an api — a raw path also reaches alpha/beta/unpublished "
        "endpoints absent from the bundled specs. Auth, signature, market, and correlation "
        "headers are added by the server. A body over the configured threshold is truncated to "
        "a preview; read the returned cached_at resource for the whole of it."
    ),
    # Passthrough to any spec operation — the caller picks the verb, so assume
    # the most cautious shape: writes, may delete, retries are not safe.
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def call_endpoint(
    region: Annotated[
        str,
        Field(description="Region label, e.g. us. Src: platforms."),
    ],
    environment: Annotated[
        str,
        Field(
            description=(
                "Target environment. walmart:marketplace accepts production or "
                "sandbox; the ads platforms accept whatever the config declares, usually "
                "production or staging. Src: platforms."
            )
        ),
    ],
    operation_id: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Operation id, qualified as api:operationId (e.g. "
                "walmart:ads:sponsored-products:SBAProfileUpdateV2) or bare when "
                "unambiguous. Resolves the api, platform, method, path, and required "
                "headers. Src: operations."
            ),
        ),
    ] = None,
    api: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Api to call, e.g. walmart:marketplace:order-management. "
                "Required with raw method+path; otherwise inferred from operation_id. "
                "Src: platforms."
            ),
        ),
    ] = None,
    method: Annotated[
        HttpMethod | None,
        Field(
            default=None,
            description="HTTP method. Required unless operation_id is given.",
        ),
    ] = None,
    path: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "API path after the base URL, e.g. /v3/orders or /api/v1/campaigns. "
                "Required unless operation_id is given."
            ),
        ),
    ] = None,
    path_params: Annotated[
        dict[str, Any] | None,
        Field(
            default=None,
            description=(
                'Values for {placeholders} in the path, e.g. {"purchaseOrderId": "1796277083022"}.'
            ),
        ),
    ] = None,
    params: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Query string parameters as a JSON object."),
    ] = None,
    body: Annotated[
        dict[str, Any] | list[dict[str, Any]] | None,
        Field(
            default=None,
            description=(
                "JSON request body for POST/PUT/PATCH — an object, or an array of objects "
                "where the API takes a batch."
            ),
        ),
    ] = None,
    file_path: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Local file to send as multipart/form-data instead of a JSON body — "
                "Marketplace feed uploads. Pair with the feedType query parameter."
            ),
        ),
    ] = None,
    advertiser_id: Annotated[
        int | None,
        Field(
            default=None,
            description=(
                "Required on walmart:marketplace, where it selects the credential "
                "to act as. On the ads platforms it is optional and sent as X-Advertiser-ID, "
                "which many display/creative/campaign endpoints require. Src: platforms."
            ),
        ),
    ] = None,
    tenant: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "WAP tenant for non-US walmart:ads regions, e.g. WMT_CA, WMT_MX, "
                "WBD_OD. Omit for US and for walmart:marketplace. Sent as wap-tenant-id."
            ),
        ),
    ] = None,
) -> ApiToolResult:
    try:
        operation, resolved_api, resolved_method, resolved_path = _resolve_target(
            operation_id, api, method, path
        )
    except (SpecError, RequestError) as e:
        return ApiToolResult(error=str(e))

    conflict = discovery.environment_conflict(resolved_api, environment)
    if conflict is not None:
        return ApiToolResult(error=conflict)

    platform = platform_of(resolved_api)
    try:
        cfg = config().env(platform, region, environment)
    except ConfigError as e:
        return ApiToolResult(error=str(e))

    try:
        response = await client.execute_request(
            cfg=cfg,
            api=resolved_api,
            method=resolved_method,
            path=resolved_path,
            operation=operation,
            params=params,
            path_params=path_params,
            body=body,
            file_path=file_path,
            advertiser_id=advertiser_id,
            tenant=tenant,
            tokens=tokens,
        )
    except (AuthError, RequestError, SpecError, ConfigError) as e:
        return ApiToolResult(error=str(e))

    cache().put(f"curl/{response.request_id}", response.curl)
    curl_ref = f"wmt://curl/{response.request_id}"

    body_str = (
        response.body
        if isinstance(response.body, str)
        else json.dumps(response.body, indent=2, ensure_ascii=False)
    )
    threshold = config().truncate_threshold

    if len(body_str.encode()) > threshold:
        cache().put(response.request_id, response.body)
        preview = body_str[:threshold].rsplit("\n", 1)[0] + "\n... (truncated)"
        return ApiToolResult(
            status_code=response.status_code,
            body=preview,
            truncated=True,
            cached_at=f"wmt://responses/{response.request_id}",
            curl=curl_ref,
        )

    return ApiToolResult(status_code=response.status_code, body=response.body, curl=curl_ref)


@mcp.tool(
    name="download_file",
    description=(
        "[Walmart] Download a report, label, or snapshot. Give a full url — such as the "
        "`details` URL from a display snapshot poll, or a Marketplace report url — or an "
        "operation_id, or an api with method and path. Written to dest_path when given, "
        "otherwise gunzipped and cached. Redirects are followed for you."
    ),
    # Writes the downloaded bytes to a local path when dest_path is given, so
    # not read-only; re-running against the same path converges.
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def download_file(
    region: Annotated[
        str,
        Field(description="Region label, e.g. us. Src: platforms."),
    ],
    environment: Annotated[
        str,
        Field(
            description=(
                "Target environment. walmart:marketplace accepts production or "
                "sandbox; the ads platforms accept whatever the config declares, usually "
                "production or staging. Src: platforms."
            )
        ),
    ],
    platform: Annotated[
        PlatformId | None,
        Field(
            default=None,
            description=(
                "Platform to authenticate as. Required with a bare url; "
                "otherwise inferred from operation_id or api. Src: platforms."
            ),
        ),
    ] = None,
    url: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Absolute URL to fetch, e.g. a snapshot or report URL returned by a previous call."
            ),
        ),
    ] = None,
    operation_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Operation id, qualified or bare. Src: operations.",
        ),
    ] = None,
    api: Annotated[
        str | None,
        Field(
            default=None,
            description="Api to call when using method+path. Src: platforms.",
        ),
    ] = None,
    method: Annotated[
        HttpMethod | None,
        Field(default=None, description="HTTP method when using path. Defaults to GET."),
    ] = None,
    path: Annotated[
        str | None,
        Field(default=None, description="API path when not using url."),
    ] = None,
    path_params: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Values for {placeholders} in path."),
    ] = None,
    params: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Query string parameters as a JSON object."),
    ] = None,
    dest_path: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Local path to write the bytes to. Omit to gunzip and cache the "
                "payload instead, readable at the returned cached_at resource."
            ),
        ),
    ] = None,
    advertiser_id: Annotated[
        int | None,
        Field(
            default=None,
            description=(
                "Required on walmart:marketplace (selects the credential) and by "
                "display snapshot downloads, where it is sent as X-Advertiser-ID and as the "
                "advertiserId query parameter. Src: platforms."
            ),
        ),
    ] = None,
    tenant: Annotated[
        str | None,
        Field(
            default=None,
            description=("WAP tenant for non-US walmart:ads regions. Sent as wap-tenant-id."),
        ),
    ] = None,
) -> DownloadToolResult:
    operation: discovery.Operation | None = None
    resolved_api = api
    resolved_method = method or "GET"
    resolved_path = path

    if operation_id is not None:
        try:
            operation = discovery.get_operation(operation_id, api=api)
        except SpecError as e:
            return DownloadToolResult(error=str(e))
        resolved_api = operation.api
        resolved_method = operation.method
        resolved_path = operation.path

    if url is None and not resolved_path:
        return DownloadToolResult(
            error="provide url, or operation_id, or api with method and path."
        )

    if resolved_api is not None:
        conflict = discovery.environment_conflict(resolved_api, environment)
        if conflict is not None:
            return DownloadToolResult(error=conflict)
        platform = platform_of(resolved_api)  # type: ignore[assignment]
    if platform is None:
        return DownloadToolResult(
            error=(
                "provide platform when downloading from a bare url "
                f"(one of: {', '.join(PLATFORM_IDS)})"
            )
        )

    try:
        cfg = config().env(platform, region, environment)
    except ConfigError as e:
        return DownloadToolResult(error=str(e))

    # Display snapshot URLs need the advertiser as a query parameter too.
    if url is not None and advertiser_id is not None and isinstance(cfg, SignatureEnv):
        params = {"advertiserId": advertiser_id, **(params or {})}

    try:
        response = await client.download(
            cfg=cfg,
            api=resolved_api,
            url=url,
            method=resolved_method,
            path=resolved_path,
            operation=operation,
            params=params,
            path_params=path_params,
            advertiser_id=advertiser_id,
            tenant=tenant,
            tokens=tokens,
        )
    except (AuthError, RequestError, SpecError, ConfigError) as e:
        return DownloadToolResult(error=str(e))

    if response.status_code != 200:
        last_url = response.urls.rsplit("→", 1)[-1].strip()
        return DownloadToolResult(
            status_code=response.status_code,
            urls=response.urls,
            error=f"Download failed: HTTP {response.status_code} at {last_url}",
        )

    if dest_path is not None:
        target = Path(dest_path).expanduser()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
        except OSError as e:
            return DownloadToolResult(
                status_code=response.status_code,
                urls=response.urls,
                error=f"cannot write {target}: {e}",
            )
        return DownloadToolResult(
            status_code=response.status_code,
            path=str(target),
            bytes_written=len(response.content),
            content_type=response.content_type,
            urls=response.urls,
        )

    try:
        text = gzip.decompress(response.content).decode()
    except (gzip.BadGzipFile, UnicodeDecodeError):
        try:
            text = response.content.decode()
        except UnicodeDecodeError:
            return DownloadToolResult(
                status_code=response.status_code,
                size_bytes=len(response.content),
                content_type=response.content_type,
                urls=response.urls,
                error="payload is binary — pass dest_path to write it to a file.",
            )

    cache().put(response.request_id, text)
    return DownloadToolResult(
        status_code=response.status_code,
        size_bytes=len(text.encode()),
        content_type=response.content_type,
        cached_at=f"wmt://responses/{response.request_id}",
        urls=response.urls,
    )


# ── refresh ────────────────────────────────────────────────────────────────────


@mcp.tool(
    name="refresh_specs",
    description=(
        "[Walmart] Refresh OpenAPI specs into the user cache, which then takes precedence over "
        "the bundled copies. Omit api to refresh all 33."
    ),
    # Writes the user spec cache: an update, not a delete — re-running it
    # against the same upstream state converges on the same cache.
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def refresh_specs(
    api: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Refresh only this api, e.g. "
                "walmart:marketplace:order-management. The two auxiliary walmart:ads specs "
                "are valid here. Src: platforms."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    try:
        results = await specs.refresh(api)
    except SpecError as e:
        return {"error": str(e)}
    written = sum(1 for r in results if r.get("status") == "written")
    return {"refreshed": written, "total": len(results), "results": results}


# ── entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
