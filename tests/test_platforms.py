from __future__ import annotations

import pytest

from mcp_walmart_ads.platforms import (
    OAUTH2,
    PLATFORM_IDS,
    PLATFORMS,
    RETAILERS,
    SIGNATURE,
    UnknownPlatform,
    platform_for,
    platform_for_api,
    platform_of,
)


def test_three_platforms_are_registered():
    assert PLATFORM_IDS == ("walmart:ads", "walmart:marketplace", "samsclub:ads")


def test_ads_platforms_sign_and_marketplace_uses_oauth2():
    assert platform_for("walmart:ads").auth == SIGNATURE
    assert platform_for("samsclub:ads").auth == SIGNATURE
    assert platform_for("walmart:marketplace").auth == OAUTH2


def test_ads_platforms_read_base_urls_from_config():
    for platform in ("walmart:ads", "samsclub:ads"):
        assert platform_for(platform).base_urls_from_config
        assert platform_for(platform).environments is None


def test_marketplace_fixes_its_hosts_and_environments():
    marketplace = platform_for("walmart:marketplace")
    assert not marketplace.base_urls_from_config
    assert marketplace.environments == ("production", "sandbox")
    assert marketplace.base_urls == {
        "production": "https://marketplace.walmartapis.com",
        "sandbox": "https://sandbox.walmartapis.com",
    }


def test_unknown_platform_names_the_known_ones():
    with pytest.raises(UnknownPlatform) as excinfo:
        platform_for("target")
    assert "walmart:ads" in str(excinfo.value)


def test_platform_of_takes_the_first_two_segments():
    assert platform_of("walmart:marketplace:order-management") == "walmart:marketplace"
    assert platform_of("samsclub:ads:sponsored-products") == "samsclub:ads"
    assert platform_of("walmart:ads:sponsored-products:SBAProfileUpdateV2") == "walmart:ads"


def test_platform_of_is_purely_structural():
    # It does not validate; resolution is platform_for's job.
    assert platform_of("nope:nope:nope") == "nope:nope"


def test_platform_for_api_resolves_through_the_prefix():
    assert platform_for_api("walmart:marketplace:order-management").auth == OAUTH2
    assert platform_for_api("samsclub:ads:sponsored-products").auth == SIGNATURE


def test_platform_for_api_rejects_an_unknown_prefix():
    with pytest.raises(UnknownPlatform):
        platform_for_api("target:ads:sponsored-products")


def test_retailers_are_deduplicated_in_declaration_order():
    assert RETAILERS == ("walmart", "samsclub")


def test_every_platform_id_is_its_two_segments():
    for platform in PLATFORMS:
        assert platform.id == f"{platform.retailer}:{platform.line}"
        assert platform.id in PLATFORM_IDS
