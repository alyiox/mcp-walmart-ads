from __future__ import annotations

import base64
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


@dataclass(frozen=True)
class Signature:
    timestamp: str
    signature: str
    key_version: str


def generate_signature(consumer_id: str, private_key_pem: str, key_version: str = "1") -> Signature:
    """Generate RSA-SHA256 auth signature matching the Walmart pre-request script logic."""
    timestamp = str(int(time.time() * 1000))

    auth_fields = {
        "WM_CONSUMER.ID": consumer_id,
        "WM_CONSUMER.INTIMESTAMP": timestamp,
        "WM_SEC.KEY_VERSION": key_version,
    }
    data_to_sign = "\n".join(auth_fields[k] for k in sorted(auth_fields)) + "\n"

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
    )
    raw_sig = private_key.sign(data_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[call-arg]
    encoded = base64.b64encode(raw_sig).decode()

    return Signature(timestamp=timestamp, signature=encoded, key_version=key_version)
