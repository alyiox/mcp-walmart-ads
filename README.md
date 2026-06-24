# Walmart Connect Advertising APIs

[![CI](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-walmart-ads.svg)](https://pypi.org/project/mcp-walmart-ads/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<!-- mcp-name: io.github.alyiox/mcp-walmart-ads -->

MCP server for [Walmart Connect Ads APIs](https://developer.walmart.com/advertising-partners) — Sponsored Search and Display.

Exposes spec-driven discovery (`list_endpoints`, `describe_endpoint`), a generic API proxy (`call_endpoint`), a runtime spec refresher (`refresh_specs`), and a display-snapshot downloader (`download_display_snapshot`). The AI agent discovers endpoints from bundled OpenAPI specs then calls them; the server handles RSA-SHA256 signing and auth headers automatically.

## Features

- **Spec-driven discovery** — list/describe endpoints from bundled OpenAPI specs, refreshable at runtime
- **Any endpoint** — call by operation id or raw method+path (raw path reaches unpublished endpoints); no code changes when APIs evolve
- Supports both Sponsored Search and Display API families
- Multi-region, multi-environment (production + staging) via config file
- Per-request RSA-SHA256 signing with automatic header construction
- Large responses truncated with full data available via MCP resource URI
- Bundled OpenAPI specs (refreshable at runtime) give the agent endpoint schemas on demand

## Requirements

- Python 3.13+
- Walmart Connect Partner Network credentials (consumer ID, RSA key pair, bearer token)

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
mkdir -p ~/.config/mcp-walmart-ads/keys/us
cp config.example.json ~/.config/mcp-walmart-ads/config.json
```

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\mcp-walmart-ads\keys\us"
Copy-Item config.example.json "$env:USERPROFILE\.config\mcp-walmart-ads\config.json"
```

**2. Edit `~/.config/mcp-walmart-ads/config.json`**

```json
{
  "response_cache_ttl": 3600,
  "truncate_threshold": 51200,
  "regions": {
    "US": {
      "production": {
        "consumer_id": "your-consumer-id",
        "private_key": "./keys/us/prod.pem",
        "private_key_version": "1",
        "bearer_token": "your-bearer-token",
        "base_urls": {
          "search": "https://developer.api.walmart.com/api-proxy/service/WPA/Api/v1",
          "display": "https://developer.api.walmart.com/api-proxy/service/display/api/v1"
        }
      },
      "staging": {
        "consumer_id": "your-staging-consumer-id",
        "private_key": "./keys/us/staging.pem",
        "private_key_version": "1",
        "bearer_token": "your-staging-bearer-token",
        "base_urls": {
          "search": "https://developer.api.stg.walmart.com/api-proxy/service/WPA/Api/v1",
          "display": "https://developer.api.us.stg.walmart.com/api-proxy/service/display/api/v1"
        }
      }
    }
  }
}
```

**3. Place your RSA private key PEM files in `~/.config/mcp-walmart-ads/keys/`**

Key paths in the config are resolved relative to the config directory, so `./keys/us/prod.pem` resolves to `~/.config/mcp-walmart-ads/keys/us/prod.pem`.

| Config field | Description |
|---|---|
| `response_cache_ttl` | Seconds to keep truncated responses in memory (default `3600`) |
| `truncate_threshold` | Response byte limit before truncation (default `51200`) |
| `regions.<R>.<E>.consumer_id` | Your Walmart Connect consumer ID |
| `regions.<R>.<E>.private_key` | Path to RSA private key PEM (relative to config dir or absolute) |
| `regions.<R>.<E>.private_key_version` | Key version string (default `"1"`) |
| `regions.<R>.<E>.bearer_token` | OAuth bearer token |
| `regions.<R>.<E>.base_urls.search` | Sponsored Search API base URL |
| `regions.<R>.<E>.base_urls.display` | Display API base URL |

## Tools

### `list_endpoints`

List operations from the bundled OpenAPI spec for an `ad_type`, with optional filters.

| Parameter | Required | Description |
|---|---|---|
| `ad_type` | yes | `search` or `display` |
| `query` | no | Case-insensitive substring match on operationId, path, or summary |
| `tag` | no | Filter to operations whose OpenAPI tags include this value |
| `method` | no | Filter by HTTP verb |

### `describe_endpoint`

Return one operation plus the `components.schemas` reachable from it (its `$ref` closure), so request bodies and responses can be built without the full spec.

| Parameter | Required | Description |
|---|---|---|
| `ad_type` | yes | `search` or `display` |
| `operation_id` | yes | Spec operation id (from `list_endpoints`) |

### `call_endpoint`

Execute any Walmart Connect Ads API endpoint. Identify it by `operation_id`, or by raw `method` + `path`. Raw method+path also reaches alpha/beta/unpublished endpoints that are not in the bundled specs. The server handles RSA-SHA256 signing.

| Parameter | Required | Description |
|---|---|---|
| `region` | yes | e.g. `US` |
| `env` | yes | `production` or `staging` |
| `ad_type` | yes | `search` or `display` |
| `operation_id` | no* | Spec operation id; resolves `method`+`path` |
| `method` | no* | `GET`, `POST`, `PUT`, `PATCH`, or `DELETE` |
| `path` | no* | e.g. `/api/v1/campaigns` |
| `params` | no | Query string parameters (JSON object) |
| `body` | no | JSON request body for POST/PUT (object or array) |

\* Provide either `operation_id`, or both `method` and `path`.

### `refresh_specs`

Re-fetch the bundled OpenAPI specs from ReadMe's public api-registry into a user cache (`~/.cache/mcp-walmart-ads/specs/`) that takes precedence over the bundled copy.

| Parameter | Required | Description |
|---|---|---|
| `spec_id` | no | One spec to refresh (e.g. `search/sponsored-products`); omit to refresh all |

### `download_display_snapshot`

Download a display snapshot file (report or entity). Display snapshot URLs require authenticated requests, so this tool handles the signing automatically. Use it with the snapshot ID from the `details` field after polling a display snapshot to `done` status.

| Parameter | Required | Description |
|---|---|---|
| `region` | yes | e.g. `US` |
| `env` | yes | `production` or `staging` |
| `snapshot_id` | yes | Snapshot ID from the `details` URL |
| `advertiser_id` | yes | Advertiser ID used when creating the snapshot |

## MCP resources

Endpoint schemas come from the bundled OpenAPI specs via `list_endpoints` / `describe_endpoint` (see [Tools](#tools)), not from static resources.

### Dynamic resources

| Resource URI | Description |
|---|---|
| `wmc://config` | Available regions, environments, and ad types from your config |
| `wmc://responses/{request_id}` | Full body of a truncated API response (cached in memory, TTL from config) |
| `wmc://curl/{request_id}` | Reproducible cURL command for a previous API request |

## MCP host examples

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "walmart-ads": {
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
    "walmart-ads": {
      "command": "uvx",
      "args": ["mcp-walmart-ads"]
    }
  }
}
```

### Codex

```toml
[mcp_servers.walmart-ads]
command = "uvx"
args = ["mcp-walmart-ads"]
```

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "walmart-ads": {
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
    "walmart-ads": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-walmart-ads"]
    }
  }
}
```

## Development

```bash
uv sync --group dev    # install deps
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run pyright         # type check
```

## Contributing

Open issues or PRs. Follow existing style and add tests where appropriate.

## License

MIT. See [LICENSE](LICENSE).
