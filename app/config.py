"""Configuration loading for oci-helper-lite-tg.

Configuration source of truth is a single YAML file. See
``docs/specs/oci-helper-lite-tg-spec.md`` §4.2 for the schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when configuration is missing required fields or fails validation."""


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8818


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowed_user_ids: frozenset[int]


@dataclass(frozen=True)
class OciProfile:
    name: str
    tenancy: str
    user: str
    fingerprint: str
    region: str
    key_file: str
    compartment_id: str

    def as_oci_sdk_config(self) -> dict[str, str]:
        """Return the shape expected by ``oci.config.validate_config``."""
        return {
            "tenancy": self.tenancy,
            "user": self.user,
            "fingerprint": self.fingerprint,
            "region": self.region,
            "key_file": self.key_file,
        }


@dataclass(frozen=True)
class OciSection:
    default_profile: str
    profiles: dict[str, OciProfile]

    def get(self, name: str | None) -> OciProfile:
        target = name or self.default_profile
        if target not in self.profiles:
            available = ", ".join(sorted(self.profiles)) or "(none)"
            raise ConfigError(
                f"Unknown OCI profile {target!r}. Available profiles: {available}"
            )
        return self.profiles[target]


@dataclass(frozen=True)
class RuntimeConfig:
    default_page_size: int = 20
    command_timeout_sec: int = 30
    confirmation_ttl_sec: int = 60
    audit_log: str = "/app/oci-helper/logs/audit.log"


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    telegram: TelegramConfig
    oci: OciSection
    runtime: RuntimeConfig
    source_path: Path = field(default=Path("/app/oci-helper/config.yml"))


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing required field {where}.{key}")
    return mapping[key]


def _parse_profile(name: str, raw: dict[str, Any]) -> OciProfile:
    where = f"oci.profiles.{name}"
    profile = OciProfile(
        name=name,
        tenancy=_require(raw, "tenancy", where),
        user=_require(raw, "user", where),
        fingerprint=_require(raw, "fingerprint", where),
        region=_require(raw, "region", where),
        key_file=_require(raw, "key_file", where),
        compartment_id=_require(raw, "compartment_id", where),
    )
    return profile


def _validate_key_file(profile: OciProfile) -> None:
    path = Path(profile.key_file)
    if not path.exists():
        raise ConfigError(
            f"key_file for profile {profile.name!r} does not exist: {profile.key_file}"
        )
    if not path.is_file():
        raise ConfigError(
            f"key_file for profile {profile.name!r} is not a regular file: {profile.key_file}"
        )
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise ConfigError(
            f"cannot stat key_file for profile {profile.name!r}: {exc}"
        ) from exc
    # Spec §4.2: "权限合理" — refuse anything world-readable.
    if mode & 0o077:
        raise ConfigError(
            f"key_file for profile {profile.name!r} has permissive mode {oct(mode)}; "
            f"expected mode <= 0o600"
        )


def load(path: str | os.PathLike[str]) -> AppConfig:
    """Load and validate the YAML config at ``path``.

    Raises:
        ConfigError: if the file is missing, unparseable, or fails schema validation.
    """
    source_path = Path(path)
    if not source_path.exists():
        raise ConfigError(f"Config file not found: {source_path}")
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML config {source_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Top-level config in {source_path} must be a mapping")

    server_raw = raw.get("server") or {}
    server = ServerConfig(
        host=str(server_raw.get("host", "0.0.0.0")),
        port=int(server_raw.get("port", 8818)),
    )

    telegram_raw = _require(raw, "telegram", "<root>")
    bot_token = _require(telegram_raw, "bot_token", "telegram")
    if not isinstance(bot_token, str) or not bot_token.strip():
        raise ConfigError("telegram.bot_token must be a non-empty string")
    allowed = telegram_raw.get("allowed_user_ids") or []
    if not isinstance(allowed, list) or not all(isinstance(x, int) for x in allowed):
        raise ConfigError("telegram.allowed_user_ids must be a list of integers")
    telegram = TelegramConfig(
        bot_token=bot_token,
        allowed_user_ids=frozenset(allowed),
    )

    oci_raw = _require(raw, "oci", "<root>")
    default_profile = _require(oci_raw, "default_profile", "oci")
    profiles_raw = _require(oci_raw, "profiles", "oci")
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ConfigError("oci.profiles must be a non-empty mapping")
    profiles = {
        name: _parse_profile(name, content) for name, content in profiles_raw.items()
    }
    if default_profile not in profiles:
        raise ConfigError(
            f"oci.default_profile {default_profile!r} is not present in oci.profiles"
        )

    for profile in profiles.values():
        _validate_key_file(profile)

    runtime_raw = raw.get("runtime") or {}
    runtime = RuntimeConfig(
        default_page_size=int(runtime_raw.get("default_page_size", 20)),
        command_timeout_sec=int(runtime_raw.get("command_timeout_sec", 30)),
        confirmation_ttl_sec=int(runtime_raw.get("confirmation_ttl_sec", 60)),
        audit_log=str(runtime_raw.get("audit_log", "/app/oci-helper/logs/audit.log")),
    )

    return AppConfig(
        server=server,
        telegram=telegram,
        oci=OciSection(default_profile=default_profile, profiles=profiles),
        runtime=runtime,
        source_path=source_path.resolve(),
    )
