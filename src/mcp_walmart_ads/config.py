from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "mcp-walmart-ads" / "config.json"


@dataclass(frozen=True)
class EnvConfig:
    consumer_id: str
    private_key_pem: str
    private_key_version: str
    bearer_token: str
    base_urls: dict[str, str]


@dataclass(frozen=True)
class Config:
    regions: dict[str, dict[str, EnvConfig]]
    response_cache_ttl: int
    truncate_threshold: int


def _resolve_key_path(raw: str, config_dir: Path) -> str:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (config_dir / p).resolve()
    return p.read_text().strip()


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        raise RuntimeError(
            f"Config file not found at {path}. Create it based on config.example.json."
        )

    raw = json.loads(path.read_text())
    config_dir = path.parent
    missing: list[str] = []
    regions: dict[str, dict[str, EnvConfig]] = {}

    for region, envs in raw.get("regions", {}).items():
        regions[region] = {}
        for env, fields in envs.items():
            prefix = f"regions.{region}.{env}"
            for required in ("consumer_id", "private_key", "bearer_token", "base_urls"):
                if not fields.get(required):
                    missing.append(f"{prefix}.{required}")

            if missing:
                continue

            try:
                pem = _resolve_key_path(fields["private_key"], config_dir)
            except (FileNotFoundError, OSError) as e:
                missing.append(f"{prefix}.private_key ({e})")
                continue

            base_urls: dict[str, str] = fields["base_urls"]
            for ad_type in ("search", "display"):
                if ad_type not in base_urls:
                    missing.append(f"{prefix}.base_urls.{ad_type}")

            regions[region][env] = EnvConfig(
                consumer_id=fields["consumer_id"],
                private_key_pem=pem,
                private_key_version=str(fields.get("private_key_version", "1")),
                bearer_token=fields["bearer_token"],
                base_urls=base_urls,
            )

    if missing:
        raise RuntimeError(
            "Config validation failed. Missing or invalid fields:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    return Config(
        regions=regions,
        response_cache_ttl=int(raw.get("response_cache_ttl", 3600)),
        truncate_threshold=int(raw.get("truncate_threshold", 51200)),
    )
