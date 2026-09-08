"""The three API families this server fronts, and what differs between them.

Each platform contributes its own OpenAPI specs (see :mod:`.specs`) to one flat
``api`` namespace, but they do not share an auth model or a way of resolving a
base URL, and those two axes are the whole reason this registry exists:

* **auth** -- Walmart Connect and Sam's Club sign every request with an
  RSA-SHA256 signature over the consumer id and a timestamp, plus a long-lived
  bearer token from the config. Marketplace runs an OAuth2 ``client_credentials``
  exchange and sends a short-lived access token.
* **base URLs** -- the ads platforms read one base URL per api from the config
  file, because Walmart hands different tenants different hosts. Marketplace's
  hosts are fixed and public, so they live here and are absent from the config.

``environments`` is ``None`` for the ads platforms: their environment names are
whatever the config declares, since a tenant may only be given one. Marketplace
validates against a closed set, because its hosts are enumerated here.
"""

from __future__ import annotations

from dataclasses import dataclass

SIGNATURE = "signature"
OAUTH2 = "oauth2"

MARKETPLACE_PRODUCTION_BASE_URL = "https://marketplace.walmartapis.com"
MARKETPLACE_SANDBOX_BASE_URL = "https://sandbox.walmartapis.com"


@dataclass(frozen=True)
class Platform:
    """One API family: how it authenticates and where its hosts come from."""

    id: str
    title: str
    auth: str
    environments: tuple[str, ...] | None = None
    base_urls: dict[str, str] | None = None

    @property
    def base_urls_from_config(self) -> bool:
        """True when the config supplies a base URL per api rather than this table."""
        return self.base_urls is None


PLATFORMS: tuple[Platform, ...] = (
    Platform("connect", "Walmart Connect Ads", SIGNATURE),
    Platform("samsclub", "Sam's Club Sponsored Ads", SIGNATURE),
    Platform(
        "marketplace",
        "Walmart Marketplace",
        OAUTH2,
        environments=("production", "sandbox"),
        base_urls={
            "production": MARKETPLACE_PRODUCTION_BASE_URL,
            "sandbox": MARKETPLACE_SANDBOX_BASE_URL,
        },
    ),
)

PLATFORM_IDS: tuple[str, ...] = tuple(p.id for p in PLATFORMS)

_BY_ID: dict[str, Platform] = {p.id: p for p in PLATFORMS}


class UnknownPlatform(Exception):
    """Raised when a platform id is not one of :data:`PLATFORM_IDS`."""


def platform_for(platform_id: str) -> Platform:
    platform = _BY_ID.get(platform_id)
    if platform is None:
        raise UnknownPlatform(
            f"unknown platform {platform_id!r} (known: {', '.join(PLATFORM_IDS)})"
        )
    return platform
