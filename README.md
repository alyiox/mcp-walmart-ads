# Walmart Connect Advertising APIs

[![CI](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/alyiox/mcp-walmart-ads/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-walmart-ads.svg)](https://pypi.org/project/mcp-walmart-ads/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

MCP server for [Walmart Connect Ads APIs](https://developer.walmart.com/advertising-partners) — Sponsored Search and Display.

Exposes a single generic tool (`walmart_ads_api`) that acts as an authenticated proxy: the AI agent decides which endpoint to call, the server handles RSA-SHA256 signing and auth headers automatically.

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

**1. Create the config directory and copy the example**

```bash
mkdir -p ~/.config/mcp-walmart-ads/keys
cp config.example.json ~/.config/mcp-walmart-ads/config.json
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
        "private_key": "./keys/us-prod.pem",
        "private_key_version": "1",
        "bearer_token": "your-bearer-token",
        "base_urls": {
          "search": "https://developer.api.walmart.com/api-proxy/service/WPA/Api/v1",
          "display": "https://developer.api.walmart.com/api-proxy/service/display/api/v1"
        }
      },
      "staging": {
        "consumer_id": "your-staging-consumer-id",
        "private_key": "./keys/us-staging.pem",
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

Key paths in the config are resolved relative to the config directory, so `./keys/us-prod.pem` resolves to `~/.config/mcp-walmart-ads/keys/us-prod.pem`.

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

## Tool: `walmart_ads_api`

Parameters shown in the client UI for user approval before execution:

| Parameter | Required | Description |
|---|---|---|
| `region` | yes | e.g. `US` |
| `env` | yes | `production` or `staging` |
| `ad_type` | yes | `search` or `display` |
| `method` | yes | `GET`, `POST`, `PUT`, `DELETE` |
| `path` | yes | e.g. `/api/v1/campaigns` |
| `params` | no | Query string parameters (JSON object) |
| `body` | no | JSON request body (for POST/PUT) |

## API reference docs (MCP resources)

The server bundles API reference docs the agent can read to learn endpoint schemas:

| Resource URI | Description |
|---|---|
| `wmc://docs/search/campaigns` | Sponsored Search campaigns |
| `wmc://docs/search/ad-groups` | Sponsored Search ad groups |
| `wmc://docs/search/keywords` | Sponsored Search keywords |
| `wmc://docs/search/snapshot-reports` | Sponsored Search snapshot reports |
| `wmc://docs/display/campaigns` | Display campaigns |
| `wmc://docs/display/snapshot-reports` | Display snapshot reports |

Truncated API responses are cached in memory and accessible via `wmc://responses/{request_id}`.

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
