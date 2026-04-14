# Walmart Connect Advertising APIs

[![CI](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-walmart-ads.svg)](https://pypi.org/project/mcp-walmart-ads/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

MCP server for [Walmart Connect Ads APIs](https://developer.walmart.com/advertising-partners) — Sponsored Search and Display.

Exposes two tools — a generic API proxy (`walmart_ads_api`) and a display-snapshot downloader (`walmart_ads_download_display_snapshot`). The AI agent decides which endpoint to call; the server handles RSA-SHA256 signing and auth headers automatically.

## Features

- **One tool, any endpoint** — no code changes needed when APIs evolve
- Supports both Sponsored Search and Display API families
- Multi-region, multi-environment (production + staging) via config file
- Per-request RSA-SHA256 signing with automatic header construction
- Large responses truncated with full data available via MCP resource URI
- Bundled API reference docs served as MCP resources so the agent knows endpoint schemas

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

### `walmart_ads_api`

Execute any Walmart Connect Ads API endpoint. The agent picks the method and path; the server handles RSA-SHA256 signing.

| Parameter | Required | Description |
|---|---|---|
| `region` | yes | e.g. `US` |
| `env` | yes | `production` or `staging` |
| `ad_type` | yes | `search` or `display` |
| `method` | yes | `GET`, `POST`, `PUT`, or `DELETE` |
| `path` | yes | e.g. `/api/v1/campaigns` |
| `params` | no | Query string parameters (JSON object) |
| `body` | no | JSON request body for POST/PUT (object or array) |

### `walmart_ads_download_display_snapshot`

Download a display snapshot file (report or entity). Display snapshot URLs require authenticated requests, so this tool handles the signing automatically. Use it with the snapshot ID from the `details` field after polling a display snapshot to `done` status.

| Parameter | Required | Description |
|---|---|---|
| `region` | yes | e.g. `US` |
| `env` | yes | `production` or `staging` |
| `snapshot_id` | yes | Snapshot ID from the `details` URL |
| `advertiser_id` | yes | Advertiser ID used when creating the snapshot |

## MCP resources

### API reference docs

The server bundles API reference docs as MCP resources so the agent can read endpoint schemas on demand. One resource per endpoint group, following the URI pattern `wmc://docs/{ad_type}/{group}` — for example `wmc://docs/search/campaigns` or `wmc://docs/display/audiences`.

The full list is generated from the markdown files in [`src/mcp_walmart_ads/docs/`](src/mcp_walmart_ads/docs/). Current groups:

| Search | Display |
|---|---|
| campaigns | campaigns |
| ad-groups | ad-groups |
| ad-items | targeting |
| keywords | audiences |
| placements | itemsets |
| bid-multipliers | itemset-campaign-association |
| sponsored-brands | catalog |
| sponsored-videos | forecast |
| catalog-item-search | creative |
| snapshot-reports | creative-associations |
| top-search-trends | video |
| advanced-insights | folder |
| stats | snapshot-reports |
| audit-snapshot | stats |
| | brand-landing-page |

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
