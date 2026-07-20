from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_walmart_ads.config import CaseInsensitiveDict, load_config


def test_case_insensitive_dict() -> None:
    d: CaseInsensitiveDict[int] = CaseInsensitiveDict({"US": 1})
    d["Mx"] = 2

    assert d["us"] == 1 and d["US"] == 1
    assert d["mx"] == 2 and d["MX"] == 2
    assert "us" in d and "MX" in d and "ca" not in d
    assert d.get("us") == 1
    assert d.get("ca") is None
    assert d.get("ca", 0) == 0
    # Original casing is preserved for display/iteration.
    assert list(d.keys()) == ["US", "Mx"]

    # Mutators route through the case-insensitive machinery too.
    d.update({"ca": 3})
    assert d["CA"] == 3
    assert d.pop("US") == 1 and "us" not in d
    del d["mx"]
    assert list(d.keys()) == ["ca"]


def _make_pem(tmp_dir: Path) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_dir / "keys" / "test.pem"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(pem)
    return key_file


def _write_config(tmp_dir: Path, data: dict) -> Path:
    config_file = tmp_dir / "config.json"
    config_file.write_text(json.dumps(data))
    return config_file


def test_load_valid_config(tmp_path: Path) -> None:
    key_file = _make_pem(tmp_path)
    cfg_data = {
        "response_cache_ttl": 1800,
        "truncate_threshold": 10000,
        "regions": {
            "US": {
                "staging": {
                    "consumer_id": "test-id",
                    "private_key": str(key_file),
                    "private_key_version": "2",
                    "bearer_token": "tok",
                    "base_urls": {
                        "search": "https://search.example.com",
                        "display": "https://display.example.com",
                    },
                }
            }
        },
    }
    cfg_file = _write_config(tmp_path, cfg_data)
    cfg = load_config(cfg_file)

    assert "US" in cfg.regions
    assert "staging" in cfg.regions["US"]
    env = cfg.regions["US"]["staging"]
    assert env.consumer_id == "test-id"
    assert env.private_key_version == "2"
    assert env.base_urls["search"] == "https://search.example.com"
    assert cfg.response_cache_ttl == 1800
    assert cfg.truncate_threshold == 10000


def test_relative_key_path(tmp_path: Path) -> None:
    key_file = _make_pem(tmp_path)
    rel = key_file.relative_to(tmp_path)
    cfg_data = {
        "regions": {
            "US": {
                "staging": {
                    "consumer_id": "id",
                    "private_key": str(rel),
                    "bearer_token": "tok",
                    "base_urls": {
                        "search": "https://s.example.com",
                        "display": "https://d.example.com",
                    },
                }
            }
        }
    }
    cfg_file = _write_config(tmp_path, cfg_data)
    cfg = load_config(cfg_file)
    assert cfg.regions["US"]["staging"].private_key_pem.startswith("-----BEGIN")


def _config_with_keys(tmp_path: Path, region: str, env: str) -> Path:
    key_file = _make_pem(tmp_path)
    cfg_data = {
        "regions": {
            region: {
                env: {
                    "consumer_id": "id",
                    "private_key": str(key_file),
                    "bearer_token": "tok",
                    "base_urls": {
                        "search": "https://s.example.com",
                        "display": "https://d.example.com",
                    },
                }
            }
        }
    }
    return _write_config(tmp_path, cfg_data)


@pytest.mark.parametrize("stored_region", ["us", "US"])
@pytest.mark.parametrize("lookup_region", ["us", "US"])
@pytest.mark.parametrize("stored_env", ["staging", "Staging"])
@pytest.mark.parametrize("lookup_env", ["staging", "STAGING"])
def test_region_and_env_lookup_case_insensitive(
    tmp_path: Path,
    stored_region: str,
    lookup_region: str,
    stored_env: str,
    lookup_env: str,
) -> None:
    cfg = load_config(_config_with_keys(tmp_path, stored_region, stored_env))
    assert lookup_region in cfg.regions
    region_envs = cfg.regions[lookup_region]
    assert lookup_env in region_envs
    assert region_envs[lookup_env].consumer_id == "id"


def test_lookup_preserves_original_key_casing(tmp_path: Path) -> None:
    cfg = load_config(_config_with_keys(tmp_path, "us", "Staging"))
    # Iteration/keys() must report keys exactly as written, not normalized.
    assert list(cfg.regions.keys()) == ["us"]
    assert list(cfg.regions["US"].keys()) == ["Staging"]


def test_missing_region_lookup(tmp_path: Path) -> None:
    cfg = load_config(_config_with_keys(tmp_path, "us", "staging"))
    assert "ca" not in cfg.regions
    assert cfg.regions.get("ca") is None


def test_missing_config_file_raises() -> None:
    with pytest.raises(RuntimeError, match="Config file not found"):
        load_config(Path("/nonexistent/config.json"))


def test_missing_required_field_raises(tmp_path: Path) -> None:
    cfg_data = {
        "regions": {
            "US": {
                "staging": {
                    "consumer_id": "id",
                    # private_key missing
                    "bearer_token": "tok",
                    "base_urls": {
                        "search": "https://s.example.com",
                        "display": "https://d.example.com",
                    },
                }
            }
        }
    }
    cfg_file = _write_config(tmp_path, cfg_data)
    with pytest.raises(RuntimeError, match="private_key"):
        load_config(cfg_file)
