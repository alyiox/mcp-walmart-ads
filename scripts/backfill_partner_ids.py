"""Fill in each Marketplace advertiser's Walmart Partner ID from the API.

Run from the repo root::

    uv run python scripts/backfill_partner_ids.py --dry-run
    uv run python scripts/backfill_partner_ids.py
    uv run python scripts/backfill_partner_ids.py --config ~/somewhere/config.json

Two ``payments`` operations require ``WM_PARTNER_ID``, and the config's
``partner_id`` is the only place this server reads it from -- a call without one
is refused before it goes out. Walmart reports the value per credential at
``GET /v3/settings/partnerprofile``, so it never has to be typed: one call per
credential fills every advertiser that credential serves, because the partner is
a property of the seller account behind the credential rather than of the
advertiser id Pacvue files it under.

Only absent values are written. A configured value that disagrees with the API
is reported and left alone: that is a question for a human. The touched file is
copied to ``backup-<timestamp>/`` beside it first, matching the convention the
config directory already uses.

Credentials that answer 403 are reported and skipped -- the seller has not
granted this scope, or the key is revoked -- so a partial result is normal and
re-running is cheap. Regenerating a config from its source of truth brings the
absent values back; this script is the repair for that, not a one-off.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from mcp_walmart_ads import client, discovery
from mcp_walmart_ads.auth import TokenManager
from mcp_walmart_ads.config import Config, OAuth2Env, load_config

PARTNER_PROFILE = "walmart:marketplace:settings-management:getPartnerConfigurations"
MARKETPLACE = "walmart:marketplace"

# One in flight per credential is pointless and 146 at once earns a 429; six
# keeps a full sweep near a minute without tripping Walmart's limiter.
CONCURRENCY = 6
RETRY_PAUSE_SECONDS = 5


async def _partner_id(
    env: OAuth2Env,
    advertiser_id: int,
    *,
    tokens: TokenManager,
    limit: asyncio.Semaphore,
) -> tuple[str | None, str | None]:
    """Return ``(partner_id, error)`` for the credential serving ``advertiser_id``."""
    operation = discovery.get_operation(PARTNER_PROFILE)
    for attempt in (1, 2):
        async with limit:
            response = await client.execute_request(
                cfg=env,
                api=operation.api,
                method=operation.method,
                path=operation.path,
                operation=operation,
                advertiser_id=advertiser_id,
                tokens=tokens,
            )
        if response.status_code == 429 and attempt == 1:
            await asyncio.sleep(RETRY_PAUSE_SECONDS)
            continue
        break

    if response.status_code != 200:
        return None, f"HTTP {response.status_code}"
    body = response.body
    if isinstance(body, str):
        body = json.loads(body)
    partner_id = ((body or {}).get("partner") or {}).get("partnerId")
    return partner_id, None if partner_id else "no partnerId in the response"


async def collect(cfg: Config) -> list[dict[str, object]]:
    """Probe every marketplace credential once, one row per advertiser."""
    tokens = TokenManager()
    limit = asyncio.Semaphore(CONCURRENCY)

    jobs: list[tuple[OAuth2Env, object]] = []
    for regions in (cfg.platforms.get(MARKETPLACE) or {}).values():
        for env in regions.values():
            if isinstance(env, OAuth2Env):
                jobs.extend((env, credential) for credential in env.credentials)

    results = await asyncio.gather(
        *(
            _partner_id(env, credential.advertisers[0].id, tokens=tokens, limit=limit)
            for env, credential in jobs
        )
    )

    rows: list[dict[str, object]] = []
    for (env, credential), (partner_id, error) in zip(jobs, results):
        for advertiser in credential.advertisers:  # type: ignore[attr-defined]
            rows.append(
                {
                    "region": env.region,
                    "environment": env.environment,
                    "advertiser": advertiser.id,
                    "existing": advertiser.partner_id,
                    "fetched": partner_id,
                    "error": error,
                }
            )
    return rows


def apply(rows: list[dict[str, object]], source: Path, *, write: bool) -> int:
    """Write absent partner ids into ``source``. Returns how many were filled."""
    fills = {
        (row["region"], row["environment"], row["advertiser"]): row["fetched"]
        for row in rows
        if row["fetched"] and not row["existing"]
    }
    if not fills or not write:
        return len(fills)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = source.parent / f"backup-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, backup / source.name)

    document = json.loads(source.read_text(encoding="utf-8"))
    filled = 0
    for platform, value in document.get("platforms", {}).items():
        if platform != MARKETPLACE:
            continue
        for region, environments in value.get("regions", {}).items():
            for environment, env in environments.items():
                for credential in env.get("credentials", []):
                    for advertiser in credential.get("advertisers", []):
                        key = (region, environment, advertiser.get("id"))
                        if fills.get(key) and not advertiser.get("partner_id"):
                            advertiser["partner_id"] = fills[key]
                            filled += 1
    source.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"backed up to {backup}")
    return filled


def report(rows: list[dict[str, object]]) -> None:
    resolved = [r for r in rows if r["fetched"]]
    agree = [r for r in resolved if r["existing"] == r["fetched"]]
    disagree = [r for r in resolved if r["existing"] and r["existing"] != r["fetched"]]
    unresolved = [r for r in rows if not r["fetched"] and not r["existing"]]

    print(f"{len(rows)} advertisers, {len(resolved)} resolved")
    print(f"  {len(agree):>3} already correct")
    print(f"  {len(unresolved):>3} still without a partner id")
    for reason, count in Counter(r["error"] for r in rows if r["error"]).most_common():
        print(f"  {count:>3} {reason}")
    for row in disagree:
        print(
            f"  MISMATCH {row['region']}/{row['advertiser']}: "
            f"config {row['existing']} vs api {row['fetched']} -- left alone"
        )


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    rest = [a for a in argv if a != "--dry-run"]
    path: Path | None = None
    if rest[:1] == ["--config"]:
        if len(rest) < 2:
            print("--config needs a path", file=sys.stderr)
            return 2
        path = Path(rest[1]).expanduser()
    elif rest:
        print(f"unknown arguments: {' '.join(rest)}", file=sys.stderr)
        return 2

    cfg = load_config(path) if path else load_config()
    source = Path(cfg.platform_sources.get(MARKETPLACE, ""))
    if not source.is_file():
        print(f"{MARKETPLACE} is not configured in {path or 'the default config'}", file=sys.stderr)
        return 1

    rows = asyncio.run(collect(cfg))
    report(rows)

    filled = apply(rows, source, write=not dry_run)
    if dry_run:
        print(f"\n--dry-run: {filled} partner id(s) would be written to {source.name}")
    else:
        print(f"\nfilled {filled} partner id(s) in {source.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
