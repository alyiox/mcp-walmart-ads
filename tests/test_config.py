from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_walmart_ads.config import load_config


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
