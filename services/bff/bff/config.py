"""BFF runtime configuration (pydantic-settings) — project_rules §19 pattern.

Single human-editable tunable file: config/bff.toml (annotated). Load precedence
(high -> low): env vars (prefix BFF_) > .env > TOML file > code defaults.
Secrets (channel API keys, auth users) live in env/.env ONLY — secret-like keys
found in the committed TOML are ignored with a warning, mirroring
services/device-service/device_service/config.py.
TOML path overridable via BFF_CONFIG_FILE (default: config/bff.toml).
"""
from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_log = logging.getLogger("bff.config")

DEFAULT_CONFIG_FILE = "config/bff.toml"
# secrets must come from env/.env only; ignored if present in the (committed) TOML
SECRET_FIELDS = frozenset({"ops_api_key", "ingest_api_key", "auth_users"})


class TomlConfigSource(PydanticBaseSettingsSource):
    """Tunables from an annotated TOML file (one level of [tables] flattened).
    Missing file -> empty (code defaults apply)."""

    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        self._data = self._load()

    @staticmethod
    def _load() -> dict:
        path = Path(os.getenv("BFF_CONFIG_FILE", DEFAULT_CONFIG_FILE))
        if not path.is_file():
            _log.info("TOML config not found at %s - using code defaults", path)
            return {}
        with path.open("rb") as fh:
            raw = tomllib.load(fh)  # malformed TOML -> fail fast at startup
        flat: dict = {}

        def _put(key: str, value) -> None:
            if key in SECRET_FIELDS:
                _log.warning("ignoring secret-like key %r in TOML; set it via .env", key)
                return
            if key in flat:
                raise ValueError(f"TOML key {key!r} appears in multiple sections")
            flat[key] = value

        for key, value in raw.items():
            if isinstance(value, dict):  # [section] table -> flatten its keys
                for k, v in value.items():
                    _put(k, v)
            else:
                _put(key, value)
        _log.info("loaded TOML config from %s (%d keys)", path, len(flat))
        return flat

    def get_field_value(self, field: FieldInfo, field_name: str):
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict:
        return dict(self._data)


class Settings(BaseSettings):
    """All tunables registered in doc/governance/tunable-parameters.md."""

    model_config = SettingsConfigDict(
        env_prefix="BFF_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- upstreams (docker service DNS names; never exposed to the browser) ---
    device_service_url: str = "http://device-service:8002"
    postgrest_url: str = "http://query:3000"
    upstream_timeout_s: float = 10.0

    # --- session (PRD-0005 §9.2 [必過]) ---
    session_cookie_name: str = "ems_bff_session"
    session_cookie_secure: bool = True  # disable only for local plain-http dev
    session_max_lifetime_s: int = 28800  # 8 h absolute cap, even with activity
    session_idle_timeout_s: int = 1800   # 30 min without a request -> invalid

    # --- CSRF (PRD-0005 §9.4: SameSite=Strict + Origin allowlist) ---
    public_origins: str = "http://localhost:8003"  # csv of exact Origin values

    # --- measurement proxy guards (§9.3 BFF-mediated PostgREST reads) ---
    measurements_default_limit: int = 100
    measurements_max_limit: int = 1000

    log_level: str = "INFO"

    # --- secrets: env/.env ONLY (SECRET_FIELDS blocks TOML) ---
    ops_api_key: str = ""      # device-service OPS channel (FR-310)
    ingest_api_key: str = ""   # device-service INGEST channel (FR-310)
    auth_users: str = ""       # "username:sha256hex:role" csv (skeleton credential store)

    @field_validator("session_max_lifetime_s", "session_idle_timeout_s")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("session lifetimes must be positive seconds")
        return v

    @field_validator("measurements_default_limit", "measurements_max_limit")
    @classmethod
    def _positive_limit(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("measurement limits must be positive")
        return v

    @model_validator(mode="after")
    def _coherent(self) -> "Settings":
        if self.session_idle_timeout_s > self.session_max_lifetime_s:
            raise ValueError("session_idle_timeout_s must not exceed session_max_lifetime_s")
        if self.measurements_default_limit > self.measurements_max_limit:
            raise ValueError("measurements_default_limit must not exceed measurements_max_limit")
        return self

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset(o.strip() for o in self.public_origins.split(",") if o.strip())

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # precedence (high -> low): init kwargs > env > .env > TOML > defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSource(settings_cls),
            file_secret_settings,
        )
