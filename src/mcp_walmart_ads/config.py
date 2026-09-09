"""Config file loading and validation.

Shape (``~/.config/mcp-walmart-ads/config.json``)::

    platforms.<platform>.regions.<region>.<environment> = <auth block>

An optional ``config.d/`` beside that file holds drop-in platform files, merged
over the base. Each may declare **only** ``platforms``, so ownership of the
server-wide scalars is never ambiguous; a platform defined in two places is an
error naming both files rather than silent precedence; and only ``*.json``
directly in the directory is read, so editor and backup litter is ignored by
construction. The point is blast radius: the marketplace block is 88% of a
populated config, and a stray comma while editing it currently takes down every
platform, because a parse failure precedes per-platform validation. Split out,
an unparseable file costs only its own platforms.

``<platform>`` is the two-segment prefix an api id starts with -- ``walmart:ads``,
``walmart:marketplace``, ``samsclub:ads`` -- so a config key is literally the
value passed as the ``platform`` tool parameter, with nothing to translate.

The auth block's shape is decided by the platform's auth model (see
:mod:`.platforms`), not by a tag in the file: there is exactly one shape per
platform, so a discriminator would only be a chance to disagree with itself.

* **signature** platforms (``walmart:ads``, ``samsclub:ads``)::

      {consumer_id, private_key, private_key_version?, bearer_token,
       base_urls: {<api>: <url>}}

  ``base_urls`` is keyed by api, either bare (``sponsored-products``) or fully
  qualified (``walmart:ads:sponsored-products``); Walmart hands different tenants
  different hosts, so these cannot be fixed by the server. One is required per api
  in the platform's discovery surface; extra keys are allowed for the auxiliary
  specs an agent reaches by raw method+path.

* **oauth2** platforms (``walmart:marketplace``)::

      {credentials: [{client_id, client_secret,
                      advertisers: [{id, partner_id?}]}]}

  Advertiser ids nest under the credential that serves them, so a secret appears
  exactly once and a dangling advertiser reference is structurally impossible.
  Partner ID is per-seller rather than per-credential because two ``payments``
  operations require it as ``WM_PARTNER_ID``. Base URLs are fixed by the server
  and absent from the file.

Regions are a namespace, not a route. For ``walmart:marketplace`` every region
reaches the same fixed hosts; the level exists because advertiser ids are only
unique within a region.

**Validation errors are isolated per platform.** A malformed
``walmart:marketplace`` block does not stop ``walmart:ads`` from loading, and
discovery -- which never touches credentials at all -- keeps working with a
config that is broken everywhere. Only a file that is missing, unparseable, or
has no ``platforms`` object at all fails outright.
"""

from __future__ import annotations

import json
from collections import UserDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from .platforms import OAUTH2, PLATFORM_IDS, platform_for
from .specs import API_IDS, SPECS

CONFIG_DIR = Path.home() / ".config" / "mcp-walmart-ads"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Drop-in directory name, resolved beside whichever config file is loaded.
CONFIG_D = "config.d"

_V = TypeVar("_V")


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or fails validation."""


class CaseInsensitiveDict(UserDict[str, _V]):
    """A mapping whose string-key lookups ignore case.

    Original key casing is preserved for iteration and display, so ``keys()``
    still reports the keys exactly as written in the config while
    ``config.regions["us"]`` and ``["US"]`` resolve alike. Building on
    :class:`~collections.UserDict` means every accessor and mutator
    (``[]``, ``in``, ``get``, ``pop`` ...) routes through ``__getitem__`` /
    ``__setitem__``, keeping the case-insensitive behavior uniform.
    """

    def __init__(self, data: Mapping[str, _V] | None = None) -> None:
        self._folded: dict[str, str] = {}
        super().__init__(data)

    def _resolve(self, key: str) -> str:
        return self._folded.get(key.casefold(), key)

    def __setitem__(self, key: str, value: _V) -> None:
        self._folded[key.casefold()] = key
        self.data[key] = value

    def __getitem__(self, key: str) -> _V:
        return self.data[self._resolve(key)]

    def __delitem__(self, key: str) -> None:
        del self.data[self._resolve(key)]
        del self._folded[key.casefold()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.casefold() in self._folded


# ── oauth2 platforms ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Advertiser:
    """One seller: its advertiser (profile) id and optional Walmart Partner ID."""

    id: int
    partner_id: str | None = None


@dataclass(frozen=True)
class Credential:
    """One client credential and the advertisers it serves."""

    client_id: str
    client_secret: str
    advertisers: tuple[Advertiser, ...]

    @property
    def advertiser_ids(self) -> tuple[int, ...]:
        return tuple(a.id for a in self.advertisers)


@dataclass(frozen=True)
class OAuth2Env:
    """One region+environment of an oauth2 platform: credentials and their index."""

    platform: str
    region: str
    environment: str
    credentials: tuple[Credential, ...]
    by_advertiser: dict[int, Credential] = field(default_factory=dict)
    advertiser_records: dict[int, Advertiser] = field(default_factory=dict)

    @property
    def advertisers(self) -> tuple[int, ...]:
        return tuple(sorted(self.by_advertiser))

    def partner_id_for(self, advertiser_id: int) -> str | None:
        """The seller's Walmart Partner ID, when the config supplies one."""
        record = self.advertiser_records.get(advertiser_id)
        return record.partner_id if record is not None else None

    def credential_for(self, advertiser_id: int) -> Credential:
        """Resolve the credential serving ``advertiser_id``.

        Raises :class:`ConfigError` naming the configured ids -- there is no
        default advertiser, so a wrong id must fail loudly.
        """
        credential = self.by_advertiser.get(advertiser_id)
        if credential is not None:
            return credential
        where = _where(self.platform, "regions", self.region, self.environment)
        if not self.by_advertiser:
            raise ConfigError(f"no credentials configured for {where}")
        known = ", ".join(str(a) for a in self.advertisers)
        raise ConfigError(
            f"advertiser {advertiser_id} not configured for {where} (configured: {known})"
        )


# ── signature platforms ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SignatureEnv:
    """One region+environment of a signature platform: its key material and hosts."""

    platform: str
    region: str
    environment: str
    consumer_id: str
    private_key_pem: str
    private_key_version: str
    bearer_token: str
    base_urls: dict[str, str]


EnvConfig = SignatureEnv | OAuth2Env


@dataclass(frozen=True)
class Config:
    """Loaded config: per-platform environments, and everything that went wrong.

    ``platform_errors`` holds validation failures for a platform that loaded;
    ``file_errors`` holds files that could not be parsed at all, which is a
    separate case because an unreadable file's platforms are unknowable -- a
    platform may be missing *because* its file did not parse, and a caller
    asking for it deserves to be told so rather than "not configured".
    """

    platforms: CaseInsensitiveDict[CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]]]
    response_cache_ttl: int
    truncate_threshold: int
    platform_errors: dict[str, list[str]] = field(default_factory=dict)
    platform_sources: dict[str, str] = field(default_factory=dict)
    file_errors: dict[str, str] = field(default_factory=dict)

    @property
    def usable(self) -> tuple[str, ...]:
        """Platforms that loaded cleanly and can serve a request."""
        return tuple(p for p in self.platforms if p not in self.platform_errors)

    def _usable_note(self) -> str:
        usable = self.usable
        return f"Usable now: {', '.join(usable)}." if usable else "No platform is usable."

    def env(self, platform: str, region: str, environment: str) -> EnvConfig:
        """Resolve one environment, or raise an error a caller can act on.

        The message leads with the remedy rather than the diagnosis: the server
        cannot repair its own config, and it reads the file once at startup, so
        an agent that retries after a fix without a restart will fail
        identically. Repeated failure shapes are collapsed and the still-usable
        platforms named, so one error answers "what now" without another call.
        """
        errors = self.platform_errors.get(platform)
        if errors:
            source = self.platform_sources.get(platform, str(CONFIG_PATH))
            raise ConfigError(
                f"{platform} is not usable: {len(errors)} config "
                f"problem{'s' if len(errors) != 1 else ''} in {source}\n"
                "Report these to the user; the server cannot fix them, and it reads the "
                "config once at startup, so a corrected file needs a server restart.\n"
                + "\n".join(f"  - {e}" for e in _collapse(_relative(platform, errors)))
                + f"\n{self._usable_note()}"
            )
        regions = self.platforms.get(platform)
        if regions is None:
            if self.file_errors:
                unreadable = ", ".join(sorted(self.file_errors))
                raise ConfigError(
                    f"{platform} is not configured, and {len(self.file_errors)} config "
                    f"file(s) could not be parsed ({unreadable}) -- it may be declared "
                    f"in one of those. Report this to the user; a fix needs a server "
                    f"restart. {self._usable_note()}"
                )
            known = ", ".join(self.platforms.keys()) or "none"
            raise ConfigError(f"platform {platform!r} is not configured (configured: {known})")
        envs = regions.get(region)
        if envs is None:
            known = ", ".join(regions.keys()) or "none"
            raise ConfigError(
                f"region {region!r} not configured for platform {platform!r} (configured: {known})"
            )
        env_cfg = envs.get(environment)
        if env_cfg is None:
            known = ", ".join(envs.keys()) or "none"
            raise ConfigError(
                f"environment {environment!r} not configured for {platform}/{region} "
                f"(configured: {known})"
            )
        return env_cfg


# ── loading ───────────────────────────────────────────────────────────────────


# How many problems to spell out before summarising the rest. A caller needs the
# shape of the failure, not an inventory: six lines differing only by region cost
# tokens and say one thing.
_MAX_REPORTED_ERRORS = 6


def _relative(platform: str, errors: list[str]) -> list[str]:
    """Drop the ``platforms."<platform>".`` prefix, which the lead line states."""
    prefix = f'platforms."{platform}".'
    return [e[len(prefix) :] if e.startswith(prefix) else e for e in errors]


def _collapse(errors: list[str]) -> list[str]:
    """Group errors sharing a message, then cap the list.

    Identical messages at different locations are one fact -- a missing keys
    directory reads as six "cannot read" lines -- so the locations are joined and
    the message stated once.
    """
    grouped: dict[str, list[str]] = {}
    for error in errors:
        location, _, message = error.partition(": ")
        grouped.setdefault(message or error, []).append(location)
    out = [
        f"{locations[0]}: {message}"
        if len(locations) == 1
        else f"{', '.join(locations)}: {message}"
        for message, locations in grouped.items()
    ]
    if len(out) > _MAX_REPORTED_ERRORS:
        hidden = len(out) - _MAX_REPORTED_ERRORS
        out = out[:_MAX_REPORTED_ERRORS] + [f"... and {hidden} more"]
    return out


# Platform ids as they were spelled before 0.2, so a stale config gets told what
# to rename rather than that its platform does not exist.
_LEGACY_PLATFORMS: dict[str, str] = {
    "connect": "walmart:ads",
    "samsclub": "samsclub:ads",
    "marketplace": "walmart:marketplace",
}


def _where(platform: str, *parts: str) -> str:
    """An error path naming a config location.

    The platform id carries a colon, so it is quoted the way it appears in the
    JSON file -- ``platforms."walmart:ads".regions.US.production``.
    """
    return ".".join((f'platforms."{platform}"', *parts))


def _surface_apis(platform: str) -> tuple[str, ...]:
    return tuple(m.spec_id for m in SPECS if m.platform == platform and m.in_surface)


def _normalize_api_key(key: str, platform: str) -> str:
    """Accept a bare name or a fully qualified api id for a base_urls key.

    Under ``walmart:ads``, both ``sponsored-products`` and
    ``walmart:ads:sponsored-products`` resolve to the same api. Anything else
    falls through as an unknown api rather than being silently reinterpreted.
    """
    if key.startswith(f"{platform}:"):
        return key
    return f"{platform}:{key}"


def _load_advertiser(raw: Any, *, where: str, errors: list[str]) -> Advertiser | None:
    """Parse an ``{"id": …, "partner_id": …}`` entry."""
    if not isinstance(raw, dict):
        errors.append(
            f'{where}: must be an object, e.g. {{"id": 7060158}} — a bare id is not accepted'
        )
        return None

    advertiser_id = raw.get("id")
    if isinstance(advertiser_id, bool) or not isinstance(advertiser_id, int):
        errors.append(f"{where}.id: required, must be an integer")
        return None

    partner_id = raw.get("partner_id")
    if partner_id is not None:
        if isinstance(partner_id, bool) or not isinstance(partner_id, (int, str)):
            errors.append(f"{where}.partner_id: must be a string or integer")
            return None
        partner_id = str(partner_id)
        if not partner_id:
            errors.append(f"{where}.partner_id: must not be empty")
            return None

    unknown = set(raw) - {"id", "partner_id"}
    if unknown:
        errors.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")

    return Advertiser(id=advertiser_id, partner_id=partner_id)


def _load_credential(raw: Any, *, where: str, errors: list[str]) -> Credential | None:
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object")
        return None

    client_id = raw.get("client_id")
    if not isinstance(client_id, str) or not client_id:
        errors.append(f"{where}.client_id: required, must be a non-empty string")
        client_id = ""

    secret = raw.get("client_secret")
    if not isinstance(secret, str) or not secret:
        errors.append(f"{where}.client_secret: required, must be a non-empty string")
        secret = ""

    raw_advertisers = raw.get("advertisers")
    advertisers: list[Advertiser] = []
    if not isinstance(raw_advertisers, list) or not raw_advertisers:
        errors.append(f"{where}.advertisers: required, must be a non-empty list")
    else:
        for index, item in enumerate(raw_advertisers):
            advertiser = _load_advertiser(
                item, where=f"{where}.advertisers[{index}]", errors=errors
            )
            if advertiser is not None:
                advertisers.append(advertiser)

    unknown = set(raw) - {"client_id", "client_secret", "advertisers"}
    if unknown:
        errors.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")

    if not client_id or not secret or not advertisers:
        return None
    return Credential(client_id=client_id, client_secret=secret, advertisers=tuple(advertisers))


def _load_oauth2_env(
    raw: Any, *, platform: str, region: str, environment: str, errors: list[str]
) -> OAuth2Env:
    where = _where(platform, "regions", region, environment)
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object")
        raw = {}

    raw_credentials = raw.get("credentials")
    credentials: list[Credential] = []
    if raw_credentials is None:
        # Allowed: a half-configured environment still loads, and fails at call
        # time. Discovery tools never touch credentials.
        raw_credentials = []
    elif not isinstance(raw_credentials, list):
        errors.append(f"{where}.credentials: must be a list")
        raw_credentials = []
    elif not raw_credentials:
        errors.append(f"{where}.credentials: must not be empty (omit the key instead)")

    for index, item in enumerate(raw_credentials):
        credential = _load_credential(item, where=f"{where}.credentials[{index}]", errors=errors)
        if credential is not None:
            credentials.append(credential)

    unknown = set(raw) - {"credentials"}
    if unknown:
        errors.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")

    index_by_advertiser: dict[int, Credential] = {}
    records: dict[int, Advertiser] = {}
    for credential in credentials:
        for advertiser in credential.advertisers:
            existing = index_by_advertiser.get(advertiser.id)
            if existing is not None:
                errors.append(
                    f"{where}: advertiser {advertiser.id} is claimed by two credentials "
                    f"({existing.client_id} and {credential.client_id})"
                )
                continue
            index_by_advertiser[advertiser.id] = credential
            records[advertiser.id] = advertiser

    return OAuth2Env(
        platform=platform,
        region=region,
        environment=environment,
        credentials=tuple(credentials),
        by_advertiser=index_by_advertiser,
        advertiser_records=records,
    )


def _load_signature_env(
    raw: Any,
    *,
    platform: str,
    region: str,
    environment: str,
    config_dir: Path,
    errors: list[str],
) -> SignatureEnv | None:
    where = _where(platform, "regions", region, environment)
    if not isinstance(raw, dict):
        errors.append(f"{where}: must be an object")
        return None

    local: list[str] = []
    for required in ("consumer_id", "private_key", "bearer_token", "base_urls"):
        if not raw.get(required):
            local.append(f"{where}.{required}: required")

    raw_base_urls = raw.get("base_urls")
    base_urls: dict[str, str] = {}
    if raw_base_urls is not None:
        if not isinstance(raw_base_urls, dict):
            local.append(f"{where}.base_urls: must be an object of api -> url")
        else:
            for key, value in raw_base_urls.items():
                api = _normalize_api_key(str(key), platform)
                if api not in API_IDS and api not in {m.spec_id for m in SPECS}:
                    local.append(f"{where}.base_urls.{key}: unknown api for platform {platform!r}")
                    continue
                if not isinstance(value, str) or not value:
                    local.append(f"{where}.base_urls.{key}: must be a non-empty URL string")
                    continue
                base_urls[api] = value
            for api in _surface_apis(platform):
                if api not in base_urls:
                    local.append(f"{where}.base_urls.{api.split(':', 2)[2]}: required")

    pem = ""
    raw_key = raw.get("private_key")
    if isinstance(raw_key, str) and raw_key:
        path = Path(raw_key).expanduser()
        if not path.is_absolute():
            path = (config_dir / path).resolve()
        try:
            pem = path.read_text(encoding="utf-8").strip()
        except OSError as e:
            # Relative to the config dir and without the errno prose: the reader
            # knows where their config lives, and identical messages collapse.
            try:
                shown = path.relative_to(config_dir)
            except ValueError:
                shown = path
            reason = "no such file" if isinstance(e, FileNotFoundError) else type(e).__name__
            local.append(f"{where}.private_key: cannot read {shown} ({reason})")
    elif raw_key is not None and not isinstance(raw_key, str):
        local.append(f"{where}.private_key: must be a path string")

    unknown = set(raw) - {
        "consumer_id",
        "private_key",
        "private_key_version",
        "bearer_token",
        "base_urls",
    }
    if unknown:
        local.append(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")

    errors.extend(local)
    if local:
        return None

    return SignatureEnv(
        platform=platform,
        region=region,
        environment=environment,
        consumer_id=str(raw["consumer_id"]),
        private_key_pem=pem,
        private_key_version=str(raw.get("private_key_version", "1")),
        bearer_token=str(raw["bearer_token"]),
        base_urls=base_urls,
    )


def _load_platform(
    raw: Any, *, platform: str, config_dir: Path, errors: list[str]
) -> CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]]:
    regions: CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]] = CaseInsensitiveDict()
    meta = platform_for(platform)

    if not isinstance(raw, dict):
        errors.append(f"{_where(platform)}: must be an object")
        return regions

    raw_regions = raw.get("regions")
    if not isinstance(raw_regions, dict) or not raw_regions:
        errors.append(f"{_where(platform, 'regions')}: required, must be a non-empty object")
        return regions

    unknown = set(raw) - {"regions"}
    if unknown:
        errors.append(f"{_where(platform)}: unknown field(s) {', '.join(sorted(unknown))}")

    for region, raw_envs in raw_regions.items():
        region_envs: CaseInsensitiveDict[EnvConfig] = CaseInsensitiveDict()
        regions[region] = region_envs
        if not isinstance(raw_envs, dict) or not raw_envs:
            errors.append(f"{_where(platform, 'regions', region)}: must be a non-empty object")
            continue
        for environment, raw_env in raw_envs.items():
            if meta.environments is not None and environment not in meta.environments:
                errors.append(
                    f"{_where(platform, 'regions', region, environment)}: unknown environment "
                    f"(expected one of {', '.join(meta.environments)})"
                )
                continue
            if meta.auth == OAUTH2:
                region_envs[environment] = _load_oauth2_env(
                    raw_env,
                    platform=platform,
                    region=region,
                    environment=environment,
                    errors=errors,
                )
            else:
                signature_env = _load_signature_env(
                    raw_env,
                    platform=platform,
                    region=region,
                    environment=environment,
                    config_dir=config_dir,
                    errors=errors,
                )
                if signature_env is not None:
                    region_envs[environment] = signature_env

    return regions


def load_config(path: Path | None = None) -> Config:
    """Load and validate the config file, reporting every problem at once.

    ``path`` is resolved at call time rather than bound as a default so the
    location stays overridable.
    """
    path = CONFIG_PATH if path is None else path
    if not path.exists():
        raise ConfigError(
            f"Config file not found at {path}. Create it based on config.example.json."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Config file at {path} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file at {path} must contain a JSON object")

    if isinstance(raw.get("regions"), dict):
        # The pre-0.2 single-platform shape. Say so, rather than reporting a
        # missing key the reader has never heard of.
        raise ConfigError(
            f"Config file at {path} uses the pre-0.2 shape (top-level 'regions'). "
            "Nest it under a platform: "
            '{"platforms": {"walmart:ads": {"regions": …}}} — one of '
            f"{', '.join(PLATFORM_IDS)}. See config.example.json."
        )

    # `platforms` may be absent here when every platform lives in config.d/,
    # which is the tidiest layout: this file then holds only server-wide
    # settings. Whether anything was configured at all is judged after the
    # drop-ins are merged.
    raw_platforms = raw.get("platforms")
    if raw_platforms is None:
        raw_platforms = {}
    elif not isinstance(raw_platforms, dict):
        raise ConfigError("platforms: must be an object")

    top_errors: list[str] = []
    platform_errors: dict[str, list[str]] = {}
    platform_sources: dict[str, str] = {}
    file_errors: dict[str, str] = {}
    platforms: CaseInsensitiveDict[CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]]]
    platforms = CaseInsensitiveDict()

    _merge_platforms(
        raw_platforms,
        source=path,
        config_dir=path.parent,
        platforms=platforms,
        platform_errors=platform_errors,
        platform_sources=platform_sources,
        top_errors=top_errors,
    )

    # Drop-in files are merged over the base. Each is parsed on its own so an
    # unreadable one costs only its own platforms, which is the whole reason the
    # directory exists.
    for extra in _drop_in_files(path):
        try:
            block = json.loads(extra.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            file_errors[str(extra)] = str(e)
            continue
        if not isinstance(block, dict):
            file_errors[str(extra)] = "must contain a JSON object"
            continue
        stray = set(block) - {"platforms"}
        if stray:
            file_errors[str(extra)] = (
                f"may declare only 'platforms'; found {', '.join(sorted(stray))}. "
                "Server-wide settings belong in config.json."
            )
            continue
        raw_extra = block.get("platforms")
        if not isinstance(raw_extra, dict) or not raw_extra:
            file_errors[str(extra)] = "platforms: required, must be a non-empty object"
            continue
        _merge_platforms(
            raw_extra,
            source=extra,
            config_dir=path.parent,
            platforms=platforms,
            platform_errors=platform_errors,
            platform_sources=platform_sources,
            top_errors=top_errors,
        )

    ttl = _positive_int(raw, "response_cache_ttl", 3600, top_errors)
    threshold = _positive_int(raw, "truncate_threshold", 1024, top_errors)

    unknown = set(raw) - {"platforms", "response_cache_ttl", "truncate_threshold"}
    if unknown:
        top_errors.append(f"unknown top-level field(s) {', '.join(sorted(unknown))}")

    if not platforms and not file_errors:
        raise ConfigError(
            f"No platform is configured. Declare one in {path} under 'platforms', or in "
            f"a {CONFIG_D}/*.json beside it — one of {', '.join(PLATFORM_IDS)}. "
            "See config.example.json."
        )

    if top_errors:
        raise ConfigError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in top_errors))

    return Config(
        platforms=platforms,
        response_cache_ttl=ttl,
        truncate_threshold=threshold,
        platform_errors=platform_errors,
        platform_sources=platform_sources,
        file_errors=file_errors,
    )


def _drop_in_files(base: Path) -> list[Path]:
    """``*.json`` directly inside ``config.d/``, sorted for a stable merge order.

    Only that exact glob: a ``.bak`` or an editor swap file beside a real config
    is litter, and silently merging one would be worse than ignoring it.
    """
    directory = base.parent / CONFIG_D
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def _merge_platforms(
    raw_platforms: dict[str, Any],
    *,
    source: Path,
    config_dir: Path,
    platforms: CaseInsensitiveDict[CaseInsensitiveDict[CaseInsensitiveDict[EnvConfig]]],
    platform_errors: dict[str, list[str]],
    platform_sources: dict[str, str],
    top_errors: list[str],
) -> None:
    """Load one file's platforms into the accumulating config.

    A platform already claimed by another file is a hard error naming both: last
    write wins would make a duplicated credential block invisible, and the point
    of splitting the config is to make a file's blast radius obvious.

    ``config_dir`` is the base config's directory for every file, not the
    declaring file's own -- so a relative ``private_key`` means the same thing
    whether its platform sits in ``config.json`` or in ``config.d/x.json``, and
    splitting an existing config needs no path edits.
    """
    for platform, raw_platform in raw_platforms.items():
        if platform not in PLATFORM_IDS:
            hint = _LEGACY_PLATFORMS.get(platform)
            detail = (
                f"renamed to {hint!r} in 0.2"
                if hint
                else f"expected one of {', '.join(PLATFORM_IDS)}"
            )
            top_errors.append(f"{source}: {_where(platform)}: unknown platform ({detail})")
            continue
        if platform in platform_sources:
            top_errors.append(
                f"platform {platform!r} is declared twice: in "
                f"{platform_sources[platform]} and {source}"
            )
            continue
        errors: list[str] = []
        platforms[platform] = _load_platform(
            raw_platform, platform=platform, config_dir=config_dir, errors=errors
        )
        platform_sources[platform] = str(source)
        if errors:
            platform_errors[platform] = errors


def _positive_int(raw: dict[str, Any], key: str, default: int, errors: list[str]) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(f"{key}: must be a positive integer")
        return default
    return value
