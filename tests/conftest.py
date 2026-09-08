"""Shared fixtures.

The RSA key is session-scoped: generating one costs ~100 ms and every signature
test only needs *a* valid key, not a distinct one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_walmart_ads.config import Advertiser, Credential, OAuth2Env, SignatureEnv


@pytest.fixture(scope="session")
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def key_file(tmp_path: Path, private_key_pem: str) -> Path:
    path = tmp_path / "key.pem"
    path.write_text(private_key_pem)
    return path


def raw_config(*, key_name: str = "key.pem") -> dict[str, Any]:
    """A complete, valid config covering all three platforms."""
    return {
        "platforms": {
            "walmart:ads": {
                "regions": {
                    "us": {
                        "production": {
                            "consumer_id": "connect-consumer",
                            "private_key": key_name,
                            "bearer_token": "connect-bearer",
                            "base_urls": {
                                "sponsored-products": "https://advertising.walmart.com",
                                "display": "https://api.dsp.walmart.com",
                            },
                        }
                    }
                }
            },
            "samsclub:ads": {
                "regions": {
                    "us": {
                        "production": {
                            "consumer_id": "sams-consumer",
                            "private_key": key_name,
                            "bearer_token": "sams-bearer",
                            "base_urls": {"sponsored-products": "https://advertising.samsclub.com"},
                        }
                    }
                }
            },
            "walmart:marketplace": {
                "regions": {
                    "us": {
                        "production": {
                            "credentials": [
                                {
                                    "client_id": "cid-1",
                                    "client_secret": "secret-1",
                                    "advertisers": [
                                        {"id": 7060158, "partner_id": "10001234"},
                                        {"id": 7060159},
                                    ],
                                }
                            ]
                        },
                        "sandbox": {
                            "credentials": [
                                {
                                    "client_id": "cid-sandbox",
                                    "client_secret": "secret-sandbox",
                                    "advertisers": [{"id": 1}],
                                }
                            ]
                        },
                    }
                }
            },
        }
    }


@pytest.fixture
def config_file(tmp_path: Path, key_file: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw_config()))
    assert key_file.exists()
    return path


@pytest.fixture
def write_config(tmp_path: Path, key_file: Path):
    """Write an arbitrary config dict and return its path."""

    def _write(data: dict[str, Any]) -> Path:
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data))
        assert key_file.exists()
        return path

    return _write


@pytest.fixture
def signature_env(private_key_pem: str) -> SignatureEnv:
    return SignatureEnv(
        platform="walmart:ads",
        region="us",
        environment="production",
        consumer_id="connect-consumer",
        private_key_pem=private_key_pem,
        private_key_version="1",
        bearer_token="connect-bearer",
        base_urls={
            "walmart:ads:sponsored-products": "https://advertising.walmart.com",
            "walmart:ads:display": "https://api.dsp.walmart.com",
        },
    )


@pytest.fixture
def credential() -> Credential:
    return Credential(
        client_id="cid-1",
        client_secret="secret-1",
        advertisers=(Advertiser(id=7060158, partner_id="10001234"), Advertiser(id=7060159)),
    )


@pytest.fixture
def oauth2_env(credential: Credential) -> OAuth2Env:
    return OAuth2Env(
        platform="walmart:marketplace",
        region="us",
        environment="production",
        credentials=(credential,),
        by_advertiser={a.id: credential for a in credential.advertisers},
        advertiser_records={a.id: a for a in credential.advertisers},
    )
