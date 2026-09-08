from __future__ import annotations

import pytest

from mcp_walmart_ads.platforms import (
    OAUTH2,
    PLATFORM_IDS,
    SIGNATURE,
    UnknownPlatform,
    platform_for,
)


def test_three_platforms_are_registered():
    assert PLATFORM_IDS == ("connect", "samsclub", "marketplace")


def test_ads_platforms_sign_and_marketplace_uses_oauth2():
    assert platform_for("connect").auth == SIGNATURE
    assert platform_for("samsclub").auth == SIGNATURE
    assert platform_for("marketplace").auth == OAUTH2


def test_ads_platforms_read_base_urls_from_config():
    for platform in ("connect", "samsclub"):
        assert platform_for(platform).base_urls_from_config
        assert platform_for(platform).environments is None


def test_marketplace_fixes_its_hosts_and_environments():
    marketplace = platform_for("marketplace")
    assert not marketplace.base_urls_from_config
    assert marketplace.environments == ("production", "sandbox")
    assert marketplace.base_urls == {
        "production": "https://marketplace.walmartapis.com",
        "sandbox": "https://sandbox.walmartapis.com",
    }


def test_unknown_platform_names_the_known_ones():
    with pytest.raises(UnknownPlatform) as excinfo:
        platform_for("target")
    assert "connect" in str(excinfo.value)
