"""The two authentication models behind the platforms this server fronts.

**Signature** (Walmart Connect, Sam's Club) -- every request carries an
RSA-SHA256 signature over the consumer id, a millisecond timestamp, and the key
version, alongside a long-lived bearer token from the config. Nothing is cached:
the signature is cheap and timestamp-bound, so it is regenerated per request.

**OAuth2** (Marketplace) -- a ``client_credentials`` grant against ``/v3/token``
with a Basic ``client_id:client_secret`` header returns an access token valid for
900 seconds, sent afterwards as ``WM_SEC.ACCESS_TOKEN``. Tokens are cached per
``(region, environment, client_id)`` -- keyed on the credential rather than the
advertiser, because several advertisers can share one credential and therefore
one token. Each key gets its own lock so a refresh for one seller never blocks
calls for another.
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .config import Credential
from .platforms import platform_for

TOKEN_PATH = "/v3/token"
MARKETPLACE_SVC_NAME = "Walmart Marketplace"

# Refresh this far ahead of expiry so an in-flight request never carries a token
# that expires mid-call.
REFRESH_MARGIN_SECONDS = 60.0

# Fallback lifetime if the response omits expires_in. Walmart documents 900s.
DEFAULT_EXPIRES_IN = 900.0


class AuthError(Exception):
    """Raised when a request cannot be authenticated."""


# ── signature (Walmart Connect, Sam's Club) ───────────────────────────────────


@dataclass(frozen=True)
class Signature:
    timestamp: str
    signature: str
    key_version: str


def generate_signature(consumer_id: str, private_key_pem: str, key_version: str = "1") -> Signature:
    """Generate the RSA-SHA256 auth signature the Walmart pre-request script defines."""
    timestamp = str(int(time.time() * 1000))

    auth_fields = {
        "WM_CONSUMER.ID": consumer_id,
        "WM_CONSUMER.INTIMESTAMP": timestamp,
        "WM_SEC.KEY_VERSION": key_version,
    }
    data_to_sign = "\n".join(auth_fields[k] for k in sorted(auth_fields)) + "\n"

    try:
        private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    except (ValueError, TypeError) as e:
        raise AuthError(f"private key is not a readable PEM private key: {e}") from e
    raw_sig = private_key.sign(data_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[call-arg]
    encoded = base64.b64encode(raw_sig).decode()

    return Signature(timestamp=timestamp, signature=encoded, key_version=key_version)


# ── OAuth2 (Marketplace) ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_at: float

    def is_fresh(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return current < self.expires_at - REFRESH_MARGIN_SECONDS


def token_url(platform: str, environment: str) -> str:
    """Token endpoint for a platform's environment.

    Always the bare environment host -- the ``/v1`` suffix that
    ``marketplace:simulations-api`` declares applies to its own operations, not
    to auth.
    """
    base_urls = platform_for(platform).base_urls
    if base_urls is None or environment not in base_urls:
        raise AuthError(f"platform {platform!r} has no token host for {environment!r}")
    return base_urls[environment] + TOKEN_PATH


def basic_auth_header(credential: Credential) -> str:
    raw = f"{credential.client_id}:{credential.client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def fetch_token(
    credential: Credential,
    platform: str,
    environment: str,
    *,
    timeout: float = 30.0,
) -> Token:
    """Exchange a client credential for an access token."""
    headers = {
        "Authorization": basic_auth_header(credential),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "WM_SVC.NAME": MARKETPLACE_SVC_NAME,
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
    }
    url = token_url(platform, environment)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                url, headers=headers, data={"grant_type": "client_credentials"}
            )
    except httpx.HTTPError as e:
        raise AuthError(f"token request to {url} failed: {e}") from e

    if response.status_code != 200:
        raise AuthError(
            f"token request to {url} returned {response.status_code}: {response.text[:400]}"
        )

    try:
        payload = response.json()
    except ValueError as e:
        raise AuthError(f"token response from {url} is not JSON: {e}") from e
    if not isinstance(payload, dict):
        raise AuthError(f"token response from {url} is not a JSON object")

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AuthError(f"token response from {url} has no access_token")

    expires_in = payload.get("expires_in")
    lifetime = float(expires_in) if isinstance(expires_in, (int, float)) else DEFAULT_EXPIRES_IN

    return Token(access_token=access_token, expires_at=time.monotonic() + lifetime)


class TokenManager:
    """Per-credential token cache with single-flight refresh."""

    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str, str, str], Token] = {}
        self._locks: dict[tuple[str, str, str, str], asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _lock_for(self, key: tuple[str, str, str, str]) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def access_token(
        self,
        credential: Credential,
        *,
        platform: str,
        region: str,
        environment: str,
        force_refresh: bool = False,
    ) -> str:
        """Return a fresh access token, fetching or refreshing as needed.

        ``force_refresh`` discards the cached token first -- used for the single
        retry after a 401, where Walmart has invalidated a token we still
        consider fresh.
        """
        key = (platform, region.casefold(), environment, credential.client_id)

        if not force_refresh:
            cached = self._tokens.get(key)
            if cached is not None and cached.is_fresh():
                return cached.access_token

        lock = await self._lock_for(key)
        async with lock:
            # Another waiter may have refreshed while we queued for the lock.
            cached = self._tokens.get(key)
            if not force_refresh and cached is not None and cached.is_fresh():
                return cached.access_token

            token = await fetch_token(credential, platform, environment)
            self._tokens[key] = token
            return token.access_token

    def invalidate(
        self, credential: Credential, *, platform: str, region: str, environment: str
    ) -> None:
        self._tokens.pop((platform, region.casefold(), environment, credential.client_id), None)
