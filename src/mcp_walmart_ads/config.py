from __future__ import annotations

import json
from collections import UserDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

CONFIG_PATH = Path.home() / ".config" / "mcp-walmart-ads" / "config.json"

_V = TypeVar("_V")


class CaseInsensitiveDict(UserDict[str, _V]):
    """A mapping whose string-key lookups ignore case.

    Original key casing is preserved for iteration and display, so ``keys()``
    still reports the keys exactly as written in the config while
    ``config.regions["us"]`` and ``["US"]`` resolve alike. Building on
    :class:`~collections.UserDict` means every accessor and mutator
    (``[]``, ``in``, ``get``, ``pop`` …) routes through ``__getitem__`` /
    ``__setitem__``, keeping the case-insensitive behavior uniform.
    """

    def __init__(self, data: Mapping[str, _V] | None = None) -> None:
        self._folded: dict[str, str] = {}
        super().__init__(data)

    def _resolve(self, key: str) -> str:
        return self._folded.get(key.casefold(), key)

    def __setitem__(self, key: str, value: _V) -> None:
        self._folded[key.casefold()] = key
        self.data[key] = value

    def __getitem__(self, key: str) -> _V:
        return self.data[self._resolve(key)]

    def __delitem__(self, key: str) -> None:
        del self.data[self._resolve(key)]
        del self._folded[key.casefold()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.casefold() in self._folded


@dataclass(frozen=True)
class EnvConfig:
    consumer_id: str
    private_key_pem: str
    private_key_version: str
    bearer_token: str
    base_urls: dict[str, str]


@dataclass(frozen=True)
class Config:
    regions: CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]]
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
    regions: CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]] = CaseInsensitiveDict()

    for region, envs in raw.get("regions", {}).items():
        region_envs: CaseInsensitiveDict[EnvConfig] = CaseInsensitiveDict()
        regions[region] = region_envs
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
