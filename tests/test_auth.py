from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_walmart_ads.auth import generate_signature


def _make_test_pem() -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_signature_returns_nonempty() -> None:
    pem = _make_test_pem()
    sig = generate_signature("test-consumer", pem, "1")
    assert sig.timestamp
    assert sig.signature
    assert sig.key_version == "1"


def test_signature_timestamp_is_ms() -> None:
    import time

    pem = _make_test_pem()
    before = int(time.time() * 1000)
    sig = generate_signature("test-consumer", pem, "1")
    after = int(time.time() * 1000)
    assert before <= int(sig.timestamp) <= after


def test_signature_is_base64() -> None:
    import base64

    pem = _make_test_pem()
    sig = generate_signature("test-consumer", pem, "1")
    decoded = base64.b64decode(sig.signature)
    assert len(decoded) == 256  # 2048-bit RSA produces 256-byte signature


def test_different_calls_produce_different_timestamps() -> None:
    import time

    pem = _make_test_pem()
    sig1 = generate_signature("test-consumer", pem, "1")
    time.sleep(0.01)
    sig2 = generate_signature("test-consumer", pem, "1")
    assert sig1.timestamp != sig2.timestamp
