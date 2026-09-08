# Walmart APIs

[![CI](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-walmart-ads.svg)](https://pypi.org/project/mcp-walmart-ads/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<!-- mcp-name: io.github.alyiox/mcp-walmart-ads -->

MCP server for three Walmart Inc. API families, behind one tool surface:

| Platform | APIs | Auth |
|---|---|---|
| `walmart:ads` — [Walmart Connect](https://developer.walmart.com/advertising-partners) | Sponsored Products, Display | RSA-SHA256 signature + bearer token |
| `walmart:marketplace` — [Walmart Marketplace](https://developer.walmart.com/home/us-mp) | 28 domains (orders, items, feeds, reports, …) | OAuth2 `client_credentials` |
| `samsclub:ads` — [Sam's Club](https://developer.samsclub.com) | Sponsored Products | RSA-SHA256 signature + bearer token |

Five tools over 31 apis and 424 operations:

```
walmart:ads:sponsored-products:SBAProfileUpdateV2
└─ retailer ─┘└ line ┘└─── api name ───┘└── operationId ──┘
   └────────── platform ─────────┘  credentials attach here
```

Spec-driven discovery (`list_endpoints`,
`describe_endpoint`), a generic API proxy (`call_endpoint`), a downloader
(`download_file`), and a runtime spec refresher (`refresh_specs`). The agent discovers
endpoints from bundled OpenAPI specs and calls them; the server handles signing, token
acquisition, and header construction.

## Features

- **Hierarchical api ids** — `<retailer>:<line>:<name>`, e.g.
  `walmart:ads:sponsored-products`, `walmart:marketplace:order-management`,
  `samsclub:ads:sponsored-products`. An operation id appends `:operationId`. Credentials
  attach at the two-segment prefix, so an operation id alone resolves to a host and an
  auth model without the caller naming either
- **Mirrored surfaces are reported** — Sam's Club mirrors Walmart Connect's
  sponsored-products API, so `wmt://apis` and `describe_endpoint` carry `mirrored_by`
  and an agent can move what it knows from one retailer to the other
- **Spec-driven discovery** — list/describe endpoints from 33 bundled OpenAPI specs,
  refreshable at runtime; `describe_endpoint` returns an operation plus its full
  `components.schemas` closure and strips the headers the server owns
- **Any endpoint** — call by operation id or raw method+path; raw paths reach
  alpha/beta/unpublished endpoints absent from the specs
- **Both auth models** — per-request RSA-SHA256 signing for the ads platforms; OAuth2
  token acquisition with per-credential caching, single-flight refresh, and one retry
  after a 401 for Marketplace
- **Per-platform config isolation** — a malformed block for one platform does not stop
  the others loading, and discovery works with no credentials at all
- **Credential-safe cURL** — every cached cURL replaces bearer tokens, access tokens,
  and signatures with placeholders
- Large responses truncated, with the full body available at an MCP resource URI

## Requirements

- Python 3.13+
- Credentials for whichever platforms you use:
  - **Walmart Connect / Sam's Club** — consumer ID, RSA key pair, bearer token
  - **Walmart Marketplace** — client ID + secret, and the advertiser (seller profile) ids they serve

## Quick start

Set up your config (see [Configuration](#configuration)), then run the server:

```bash
# Run directly with uvx (no clone needed)
npx -y @modelcontextprotocol/inspector uvx mcp-walmart-ads
```

```bash
# Or run from source
git clone https://github.com/alyiox/mcp-walmart-ads.git
cd mcp-walmart-ads
uv sync
npx -y @modelcontextprotocol/inspector uv run mcp-walmart-ads
```

## Configuration

The config file lives under your home directory at `~/.config/mcp-walmart-ads/config.json`.

> **Windows note:** `~` maps to `%USERPROFILE%` (typically `C:\Users\<you>`), so the
> full path is `%USERPROFILE%\.config\mcp-walmart-ads\config.json`.

**1. Create the config directory and copy the example**

```bash
# Unix-like (macOS, Linux, WSL, …)
mkdir -p ~/.config/mcp-walmart-ads/keys/walmart-ads
cp config.example.json ~/.config/mcp-walmart-ads/config.json
```

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\mcp-walmart-ads\keys\walmart-ads"
Copy-Item config.example.json "$env:USERPROFILE\.config\mcp-walmart-ads\config.json"
```

**2. Fill in your credentials.** Configure only the platforms you use — an absent
platform is simply unconfigured, and the discovery tools keep working regardless.

### Shape

```
platforms.<platform>.regions.<region>.<environment> = <auth block>
```

`<platform>` is the two-segment prefix an api id starts with, so a config key is literally
the value you pass as the `platform` tool parameter — nothing to translate.

The auth block's shape follows the platform's auth model. There is exactly one shape per
platform, so no discriminator field is needed.

**Signature platforms** (`walmart:ads`, `samsclub:ads`):

```json
{
  "platforms": {
    "walmart:ads": {
      "regions": {
        "us": {
          "production": {
            "consumer_id": "your-consumer-id",
            "private_key": "./keys/walmart-ads/us-prod.pem",
            "private_key_version": "1",
            "bearer_token": "your-bearer-token",
            "base_urls": {
              "sponsored-products": "https://developer.api.walmart.com/api-proxy/service/WPA/Api/v1",
              "display": "https://developer.api.walmart.com/api-proxy/service/display/api/v1"
            }
          }
        }
      }
    }
  }
}
```

| Field | Notes |
|---|---|
| `consumer_id` | Partner Network consumer ID |
| `private_key` | Path to the RSA private key (PEM); relative paths resolve against the config directory |
| `private_key_version` | Key version string (default `"1"`) |
| `bearer_token` | OAuth bearer token |
| `base_urls.<api>` | One per api in the platform's discovery surface. Keys may be bare (`sponsored-products`) or fully qualified (`walmart:ads:sponsored-products`). Extra keys are allowed for the auxiliary specs reached by raw method+path |

Environment names are free-form for these platforms — Walmart may issue a tenant only
`production`, or `production` + `staging`.

**OAuth2 platform** (`walmart:marketplace`):

```json
{
  "platforms": {
    "walmart:marketplace": {
      "regions": {
        "us": {
          "production": {
            "credentials": [
              {
                "client_id": "your-client-id",
                "client_secret": "your-client-secret",
                "advertisers": [
                  { "id": 7060158, "partner_id": "10001234" },
                  { "id": 7060159 }
                ]
              }
            ]
          }
        }
      }
    }
  }
}
```

Advertiser ids nest under the credential that serves them, so a secret appears exactly
once and a dangling advertiser reference is structurally impossible. `partner_id` is
per-seller because two `payments` operations require it as `WM_PARTNER_ID`. Base URLs are
fixed by the server and absent from the file; `environment` must be `production` or
`sandbox`.

Regions are a namespace, not a route — for `walmart:marketplace` every region reaches the
same hosts. The level exists because advertiser ids are only unique within a region.

### Top-level options

| Field | Default | Notes |
|---|---|---|
| `response_cache_ttl` | `3600` | Seconds a truncated body or download stays readable at its resource URI |
| `truncate_threshold` | `1024` | Response bytes returned inline before truncating to a preview |

### Market → tenant (`wap-tenant-id`)

Pass `tenant` on `call_endpoint` / `download_file` for non-US `walmart:ads` markets
(e.g. `WMT_CA`, `WMT_MX`, `WBD_OD`). Omit for US and for `walmart:marketplace`.

## Tools

### `list_endpoints`

List operations across every api, with optional filters.

| Parameter | Notes |
|---|---|
| `query` | Case-insensitive substring on operation id, path, or summary |
| `api` | Limit to one api, e.g. `walmart:marketplace:order-management` |
| `platform` | Limit to one platform — `walmart:ads`, `walmart:marketplace`, `samsclub:ads` (schema enum) |
| `tag` | Filter by OpenAPI tag |
| `method` | Filter by HTTP verb — `GET`, `POST`, `PUT`, `PATCH`, `DELETE` (schema enum) |

Returned operation ids are qualified (`api:operationId`) and can be passed straight to
`describe_endpoint` or `call_endpoint`.

### `describe_endpoint`

One operation plus every `components.schemas` entry reachable from it, so request bodies
can be built without the full spec. Server-managed auth and QoS headers are omitted.

| Parameter | Notes |
|---|---|
| `operation_id` | Qualified (`api:operationId`) or bare when unambiguous |
| `api` | Api to resolve a bare id in, e.g. `walmart:ads:sponsored-products` |

### `call_endpoint`

Execute an authenticated request against any configured platform.

| Parameter | Notes |
|---|---|
| `region`, `environment` | Required. Src: config |
| `operation_id` | Qualified or bare. Resolves api, platform, method, path, and required headers |
| `api` | Required with raw `method` + `path`; otherwise inferred from `operation_id`. Accepts the two auxiliary `walmart:ads` specs |
| `method`, `path` | Raw route, reaching endpoints absent from the specs |
| `path_params` | Values for `{placeholders}` in the path |
| `params`, `body` | Query string and JSON body |
| `file_path` | Send the file as `multipart/form-data` — Marketplace feed uploads. Pair with the `feedType` query parameter |
| `advertiser_id` | **Required on `walmart:marketplace`**, where it selects the credential. Optional on the ads platforms, where it is sent as `X-Advertiser-ID` |
| `tenant` | WAP tenant for non-US `walmart:ads` regions |

### `download_file`

Download a report, label, or snapshot from an authenticated endpoint. Give a full `url`
(e.g. the `details` URL from a display snapshot poll), or `operation_id`, or `api` with
`method` + `path`.

With `dest_path` the bytes are written there. Without it they are gunzipped when gzipped
and cached, and the result carries `cached_at` — a binary payload with no `dest_path`
asks for one instead. Redirects are followed, keeping auth headers on a relative or
same-host `Location` and dropping credentials cross-host; the result includes `urls`, the
hop path. `platform` is required only when downloading from a bare `url`.

### `refresh_specs`

Re-fetch bundled specs into a user cache that then takes precedence over the bundled
copies. Pass `api` to refresh one — e.g. `walmart:marketplace:order-management` — or omit
to refresh all 33, the two auxiliary `walmart:ads` specs included.

## MCP resources

| Resource URI | Description |
|---|---|
| `wmt://config` | Configured platforms, regions, environments, and their advertiser ids or api base URLs |
| `wmt://apis` | The api namespace — every api id, its platform, environments, operation count, and `mirrored_by` where another retailer serves the same surface |
| `wmt://responses/{request_id}` | Full body of a truncated response or a cached download (in memory, TTL from config) |
| `wmt://curl/{request_id}` | Reproducible cURL for a previous request, credentials replaced with placeholders |

## MCP host examples

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "walmart": {
      "command": "uvx",
      "args": ["mcp-walmart-ads"]
    }
  }
}
```

### Claude Code

Add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "walmart": {
      "command": "uvx",
      "args": ["mcp-walmart-ads"]
    }
  }
}
```

### Codex

```toml
[mcp_servers.walmart]
command = "uvx"
args = ["mcp-walmart-ads"]
```

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "walmart": {
      "type": "local",
      "enabled": true,
      "command": ["uvx", "mcp-walmart-ads"]
    }
  }
}
```

### GitHub Copilot

```json
{
  "inputs": [],
  "servers": {
    "walmart": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-walmart-ads"]
    }
  }
}
```

## Where the specs come from

Walmart publishes no OpenAPI files, but each ReadMe reference page hydrates its HTML with
the registry UUIDs of its documents, and `https://dash.readme.com/api/v1/api-registry/<uuid>`
serves the full spec unauthenticated. That covers Walmart Connect and all 28 Marketplace
domains. Sam's Club publishes neither, so its spec is hand-authored from the developer
docs; `scripts/build_samsclub_spec.py` regenerates a *candidate* from those docs and the
scheduled `spec drift` workflow opens a PR when they change, as a human review gate. The
candidate is never shipped and never loaded at runtime.

Specs are stored verbatim as upstream served them, so a refresh diff shows exactly what
changed; oversized inline examples and `x-readme` metadata are stripped on load rather
than on disk.

```bash
# Rebuild the bundled specs (registry-sourced only, by default)
uv run python scripts/fetch_specs.py
uv run python scripts/fetch_specs.py walmart:ads:sponsored-products walmart:marketplace:order-management

# Regenerate the Sam's Club candidate spec for review
uv run --group spec-build python scripts/build_samsclub_spec.py
```

## Development

```bash
uv sync --group dev
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run pyright
uv run pytest tests/ -v
```

## Contributing

Issues and pull requests are welcome. Please keep changes focused and make sure
`ruff check`, `ruff format --check`, `pyright`, and `pytest` all pass.

## License

MIT — see [LICENSE](LICENSE).
