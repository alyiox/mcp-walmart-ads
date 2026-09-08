from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_walmart_ads.config import (
    CaseInsensitiveDict,
    ConfigError,
    OAuth2Env,
    SignatureEnv,
    load_config,
)
from tests.conftest import raw_config

# ── CaseInsensitiveDict ───────────────────────────────────────────────────────


def test_lookup_ignores_case_but_preserves_the_written_key():
    d: CaseInsensitiveDict[int] = CaseInsensitiveDict({"US": 1})
    assert d["us"] == d["US"] == d["Us"] == 1
    assert list(d.keys()) == ["US"]
    assert "us" in d and "nope" not in d


def test_deletion_and_reassignment_stay_case_insensitive():
    d: CaseInsensitiveDict[int] = CaseInsensitiveDict({"US": 1})
    d["us"] = 2
    assert d["US"] == 2
    del d["Us"]
    assert "us" not in d


def test_non_string_keys_are_simply_absent():
    d: CaseInsensitiveDict[int] = CaseInsensitiveDict({"a": 1})
    assert 7 not in d


# ── happy path ────────────────────────────────────────────────────────────────


def test_all_three_platforms_load(config_file: Path):
    cfg = load_config(config_file)
    assert set(cfg.platforms.keys()) == {"walmart:ads", "samsclub:ads", "walmart:marketplace"}
    assert cfg.platform_errors == {}


def test_signature_platform_resolves_key_material_and_hosts(config_file: Path):
    env = load_config(config_file).env("walmart:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert env.consumer_id == "connect-consumer"
    assert env.bearer_token == "connect-bearer"
    assert env.private_key_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert env.private_key_version == "1"


def test_base_url_keys_accept_bare_or_qualified_api_names(config_file: Path):
    env = load_config(config_file).env("walmart:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert env.base_urls == {
        "walmart:ads:sponsored-products": "https://advertising.walmart.com",
        "walmart:ads:display": "https://api.dsp.walmart.com",
    }


def test_qualified_base_url_keys_round_trip(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["base_urls"] = {
        "walmart:ads:sponsored-products": "https://a.test",
        "walmart:ads:display": "https://b.test",
    }
    env = load_config(write_config(data)).env("walmart:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert set(env.base_urls) == {"walmart:ads:sponsored-products", "walmart:ads:display"}


def test_an_auxiliary_api_may_also_carry_a_base_url(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["base_urls"][
        "walmart:ads:conversions"
    ] = "https://c.test"
    env = load_config(write_config(data)).env("walmart:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert env.base_urls["walmart:ads:conversions"] == "https://c.test"


def test_oauth2_platform_indexes_advertisers_by_credential(config_file: Path):
    env = load_config(config_file).env("walmart:marketplace", "us", "production")
    assert isinstance(env, OAuth2Env)
    assert env.advertisers == (7060158, 7060159)
    assert env.credential_for(7060158).client_id == "cid-1"
    assert env.credential_for(7060159) is env.credential_for(7060158)
    assert env.partner_id_for(7060158) == "10001234"
    assert env.partner_id_for(7060159) is None


def test_region_and_environment_lookup_is_case_insensitive(config_file: Path):
    cfg = load_config(config_file)
    assert cfg.env("WALMART:ADS", "US", "production") is cfg.env("walmart:ads", "us", "production")


def test_relative_private_key_path_resolves_against_the_config_dir(config_file: Path):
    env = load_config(config_file).env("samsclub:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert env.private_key_pem


def test_absolute_private_key_path_is_used_as_given(write_config, key_file: Path):
    data = raw_config()
    data["platforms"]["samsclub:ads"]["regions"]["us"]["production"]["private_key"] = str(key_file)
    env = load_config(write_config(data)).env("samsclub:ads", "us", "production")
    assert isinstance(env, SignatureEnv)
    assert env.private_key_pem


def test_thresholds_default_and_override(write_config):
    assert load_config(write_config(raw_config())).truncate_threshold == 1024
    data = raw_config() | {"truncate_threshold": 4096, "response_cache_ttl": 60}
    cfg = load_config(write_config(data))
    assert (cfg.truncate_threshold, cfg.response_cache_ttl) == (4096, 60)


# ── file-level failures ───────────────────────────────────────────────────────


def test_missing_config_file_raises(tmp_path: Path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path / "absent.json")
    assert "config.example.json" in str(excinfo.value)


def test_unparseable_config_raises(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text("{oops")
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "not valid JSON" in str(excinfo.value)


def test_non_object_config_raises(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text("[]")
    with pytest.raises(ConfigError):
        load_config(path)


def test_missing_platforms_key_raises(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"response_cache_ttl": 60}))
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    assert "platforms: required" in str(excinfo.value)


def test_unknown_platform_and_unknown_top_level_field_fail_the_file(write_config):
    data = raw_config()
    data["platforms"]["target"] = {"regions": {}}
    data["extra"] = 1
    with pytest.raises(ConfigError) as excinfo:
        load_config(write_config(data))
    message = str(excinfo.value)
    assert "unknown platform" in message
    assert "unknown top-level field" in message


def test_bad_threshold_fails_the_file(write_config):
    with pytest.raises(ConfigError) as excinfo:
        load_config(write_config(raw_config() | {"truncate_threshold": 0}))
    assert "positive integer" in str(excinfo.value)


# ── per-platform error isolation ──────────────────────────────────────────────


def test_a_broken_platform_does_not_stop_the_others(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"]["credentials"][0].pop(
        "client_secret"
    )
    cfg = load_config(write_config(data))
    assert "walmart:marketplace" in cfg.platform_errors
    for platform, consumer_id in (
        ("walmart:ads", "connect-consumer"),
        ("samsclub:ads", "sams-consumer"),
    ):
        env = cfg.env(platform, "us", "production")
        assert isinstance(env, SignatureEnv)
        assert env.consumer_id == consumer_id


def test_a_broken_platform_fails_only_when_used(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"].pop("bearer_token")
    cfg = load_config(write_config(data))
    with pytest.raises(ConfigError) as excinfo:
        cfg.env("walmart:ads", "us", "production")
    assert "bearer_token" in str(excinfo.value)
    assert cfg.env("walmart:marketplace", "us", "production")


def test_every_error_for_a_platform_is_reported_together(write_config):
    data = raw_config()
    env = data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"]
    env["credentials"][0].pop("client_secret")
    env["credentials"].append(
        {"client_id": "dup", "client_secret": "x", "advertisers": [{"id": 7060159}]}
    )
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["staging"] = {"credentials": []}
    errors = load_config(write_config(data)).platform_errors["walmart:marketplace"]
    assert any("client_secret" in e for e in errors)
    assert any("unknown environment" in e for e in errors)


def test_signature_platform_reports_every_missing_field_at_once(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"] = {"base_urls": {}}
    errors = load_config(write_config(data)).platform_errors["walmart:ads"]
    joined = "\n".join(errors)
    for field in ("consumer_id", "private_key", "bearer_token", "sponsored-products", "display"):
        assert field in joined


def test_an_unreadable_private_key_is_reported_not_raised(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["private_key"] = "absent.pem"
    cfg = load_config(write_config(data))
    assert any("cannot read" in e for e in cfg.platform_errors["walmart:ads"])


def test_a_missing_surface_api_base_url_is_reported(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["base_urls"] = {
        "search": "https://a.test"
    }
    errors = load_config(write_config(data)).platform_errors["walmart:ads"]
    assert any("base_urls.display: required" in e for e in errors)


def test_an_unknown_base_url_api_is_reported(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["production"]["base_urls"]["nope"] = (
        "https://x"
    )
    errors = load_config(write_config(data)).platform_errors["walmart:ads"]
    assert any("unknown api" in e for e in errors)


def test_unknown_environment_for_a_closed_platform_is_reported(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["staging"] = {"credentials": []}
    errors = load_config(write_config(data)).platform_errors["walmart:marketplace"]
    assert any("unknown environment" in e for e in errors)


def test_an_open_platform_accepts_any_environment_name(write_config):
    data = raw_config()
    data["platforms"]["walmart:ads"]["regions"]["us"]["staging"] = data["platforms"]["walmart:ads"][
        "regions"
    ]["us"]["production"]
    cfg = load_config(write_config(data))
    assert cfg.platform_errors == {}
    assert cfg.env("walmart:ads", "us", "staging")


def test_two_credentials_claiming_one_advertiser_is_reported(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"]["credentials"].append(
        {"client_id": "cid-2", "client_secret": "s", "advertisers": [{"id": 7060158}]}
    )
    errors = load_config(write_config(data)).platform_errors["walmart:marketplace"]
    assert any("claimed by two credentials" in e for e in errors)


def test_a_bare_advertiser_id_is_rejected(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"]["credentials"][0][
        "advertisers"
    ] = [7060158]
    errors = load_config(write_config(data)).platform_errors["walmart:marketplace"]
    assert any("must be an object" in e for e in errors)


def test_advertiser_rejects_unknown_fields(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"]["credentials"][0][
        "advertisers"
    ] = [{"id": 1, "nickname": "x"}]
    errors = load_config(write_config(data)).platform_errors["walmart:marketplace"]
    assert any("unknown field" in e for e in errors)


def test_an_environment_with_no_credentials_loads_and_fails_at_call_time(write_config):
    data = raw_config()
    data["platforms"]["walmart:marketplace"]["regions"]["us"]["production"] = {}
    cfg = load_config(write_config(data))
    assert cfg.platform_errors == {}
    env = cfg.env("walmart:marketplace", "us", "production")
    assert isinstance(env, OAuth2Env)
    with pytest.raises(ConfigError) as excinfo:
        env.credential_for(7060158)
    assert "no credentials configured" in str(excinfo.value)


# ── lookup failures ───────────────────────────────────────────────────────────


def test_unconfigured_platform_region_and_environment_each_name_alternatives(config_file: Path):
    cfg = load_config(config_file)
    with pytest.raises(ConfigError) as excinfo:
        cfg.env("walmart:marketplace", "eu", "production")
    assert "us" in str(excinfo.value)
    with pytest.raises(ConfigError) as excinfo:
        cfg.env("walmart:marketplace", "us", "sandbox2")
    assert "production" in str(excinfo.value)


def test_a_platform_absent_from_the_file_is_reported_as_unconfigured(write_config):
    data = raw_config()
    del data["platforms"]["samsclub:ads"]
    cfg = load_config(write_config(data))
    with pytest.raises(ConfigError) as excinfo:
        cfg.env("samsclub:ads", "us", "production")
    assert "not configured" in str(excinfo.value)


def test_unknown_advertiser_names_the_configured_ids(config_file: Path):
    env = load_config(config_file).env("walmart:marketplace", "us", "production")
    assert isinstance(env, OAuth2Env)
    with pytest.raises(ConfigError) as excinfo:
        env.credential_for(999)
    assert "7060158" in str(excinfo.value)


# ── migration hints ───────────────────────────────────────────────────────────


def test_the_pre_0_2_config_shape_is_named_explicitly(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"regions": {"US": {"production": {"consumer_id": "x"}}}}))
    with pytest.raises(ConfigError) as excinfo:
        load_config(path)
    message = str(excinfo.value)
    assert "pre-0.2 shape" in message
    assert "walmart:ads" in message


def test_a_legacy_platform_key_is_told_its_new_name(write_config):
    for legacy, current in (
        ("connect", "walmart:ads"),
        ("samsclub", "samsclub:ads"),
        ("marketplace", "walmart:marketplace"),
    ):
        data = raw_config()
        data["platforms"][legacy] = data["platforms"].pop(current)
        with pytest.raises(ConfigError) as excinfo:
            load_config(write_config(data))
        assert f"renamed to {current!r}" in str(excinfo.value)
