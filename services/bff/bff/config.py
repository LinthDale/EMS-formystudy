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
SECRET_FIELDS = frozenset(
    {"ops_api_key", "ingest_api_key", "auth_users", "oidc_client_secret"}
)


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

    # --- auth provider (ADR-024): local argon2id fallback (default) | oidc ---
    auth_mode: str = "local"  # "local" -> argon2id user table; "oidc" -> enterprise IdP

    # --- OIDC (ADR-024 Phase-1; Authorization-Code + PKCE). Only consulted when
    #     auth_mode == "oidc"; issuer/client_id/redirect are fail-fast required then. ---
    oidc_issuer: str = ""          # IdP issuer URL; discovery = {issuer}/.well-known/openid-configuration
    oidc_client_id: str = ""       # registered confidential client id
    oidc_redirect_uri: str = ""    # absolute callback URL registered at the IdP -> /api/auth/oidc/callback
    oidc_scopes: str = "openid profile email"  # space-separated; must include openid
    oidc_role_claim: str = "groups"            # id-token claim carrying the role/group values
    # claim value -> Role map, csv "claimval:role" (role = ops|ingest|readonly).
    # Unknown/empty claim -> reject (fail closed, no default privilege).
    oidc_role_map: str = ""
    # transient login state (PKCE verifier / state / nonce) TTL — short by design.
    oidc_state_ttl_s: int = 300  # 5 min to complete the redirect round-trip
    # where the callback sends the browser after a successful login (SPA entry).
    # Same-origin path by default so it cannot be turned into an open redirect.
    oidc_post_login_redirect: str = "/"

    # --- session (PRD-0005 §9.2 [必過]) ---
    session_cookie_name: str = "ems_bff_session"
    session_cookie_secure: bool = True  # disable only for local plain-http dev
    session_max_lifetime_s: int = 28800  # 8 h absolute cap, even with activity
    session_idle_timeout_s: int = 1800   # 30 min without a request -> invalid
    # In-memory store janitor: validate() evicts lazily on access, but never-
    # re-accessed sessions would otherwise accumulate; a background task sweeps
    # them on this interval (ADR-023 in-memory P1 store; code-review MED).
    session_sweep_interval_s: int = 300  # 5 min

    # --- CSRF (PRD-0005 §9.4: SameSite=Strict + Origin allowlist) ---
    public_origins: str = "http://localhost:8003"  # csv of exact Origin values

    # --- measurement proxy guards (§9.3 BFF-mediated PostgREST reads) ---
    measurements_default_limit: int = 100
    measurements_max_limit: int = 1000

    log_level: str = "INFO"

    # --- secrets: env/.env ONLY (SECRET_FIELDS blocks TOML) ---
    ops_api_key: str = ""      # device-service OPS channel (FR-310)
    ingest_api_key: str = ""   # device-service INGEST channel (FR-310)
    auth_users: str = ""       # "username:<argon2id PHC>:role" csv (local fallback, ADR-024)
    oidc_client_secret: str = ""  # OIDC confidential client secret (ADR-024)

    @field_validator("auth_mode")
    @classmethod
    def _known_auth_mode(cls, v: str) -> str:
        mode = v.strip().lower()
        if mode not in {"local", "oidc"}:
            raise ValueError("auth_mode must be 'local' or 'oidc'")
        return mode

    @field_validator(
        "session_max_lifetime_s", "session_idle_timeout_s", "session_sweep_interval_s"
    )
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

    @field_validator("oidc_state_ttl_s")
    @classmethod
    def _positive_ttl(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("oidc_state_ttl_s must be a positive number of seconds")
        return v

    @field_validator("oidc_post_login_redirect")
    @classmethod
    def _safe_post_login_redirect(cls, v: str) -> str:
        # Same-origin path ONLY (the callback hands this straight to RedirectResponse):
        # a single leading '/', and not '//...' (protocol-relative) nor '/\...'. This
        # is the fail-fast that backs the field's "cannot be an open redirect" intent —
        # a misconfigured https://evil or //evil would otherwise be an open redirect
        # after a successful OIDC login (routes/oidc.py).
        if not v.startswith("/") or v.startswith("//") or v.startswith("/\\"):
            raise ValueError(
                "oidc_post_login_redirect must be a same-origin path starting with a single '/'"
            )
        return v

    @model_validator(mode="after")
    def _coherent(self) -> "Settings":
        if self.session_idle_timeout_s > self.session_max_lifetime_s:
            raise ValueError("session_idle_timeout_s must not exceed session_max_lifetime_s")
        if self.measurements_default_limit > self.measurements_max_limit:
            raise ValueError("measurements_default_limit must not exceed measurements_max_limit")
        # Fail fast: oidc mode is unusable without an issuer + client id + redirect.
        # (No silent degradation to an insecure path — mirrors ADR-024 fail-closed.)
        if self.auth_mode == "oidc":
            missing = [
                name
                for name, value in (
                    ("BFF_OIDC_ISSUER", self.oidc_issuer),
                    ("BFF_OIDC_CLIENT_ID", self.oidc_client_id),
                    ("BFF_OIDC_REDIRECT_URI", self.oidc_redirect_uri),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(
                    "BFF_AUTH_MODE=oidc requires " + ", ".join(missing)
                )
            # discovery / token exchange / redirect are high-sensitivity hops — require
            # https, allowing http only for localhost/127.0.0.1 (dev). Prevents an
            # accidental cleartext IdP endpoint or redirect URI in a real deployment.
            from urllib.parse import urlparse
            for _label, _url in (("BFF_OIDC_ISSUER", self.oidc_issuer),
                                 ("BFF_OIDC_REDIRECT_URI", self.oidc_redirect_uri)):
                _p = urlparse(_url)
                _local = (_p.hostname or "") in {"localhost", "127.0.0.1", "::1"}
                if not (_p.scheme == "https" or (_p.scheme == "http" and _local)):
                    raise ValueError(
                        f"{_label} must be https:// (http:// allowed only for localhost/127.0.0.1 dev)"
                    )
            if "openid" not in self.oidc_scope_list:
                raise ValueError("oidc_scopes must include 'openid'")
            if not self.oidc_role_mapping:
                raise ValueError(
                    "BFF_AUTH_MODE=oidc requires a non-empty BFF_OIDC_ROLE_MAP "
                    "(claimval:role csv); unmapped claims are rejected (fail closed)"
                )
        return self

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset(o.strip() for o in self.public_origins.split(",") if o.strip())

    @property
    def oidc_scope_list(self) -> tuple[str, ...]:
        return tuple(s for s in self.oidc_scopes.split() if s)

    @property
    def oidc_role_mapping(self) -> dict[str, str]:
        """Parse ``claimval:role`` csv into an immutable-style dict (fresh each call).

        Returns ``{claim_value: role_str}``. A malformed entry, an unknown role, or a
        duplicate claim value fails fast so a typo can never silently grant or drop
        privilege. Role validity is re-checked by the OIDC provider against the Role
        enum (this layer stays enum-agnostic to avoid an import cycle)."""
        mapping: dict[str, str] = {}
        for entry in self.oidc_role_map.split(","):
            entry = entry.strip()
            if not entry:
                continue
            claim_value, sep, role = entry.partition(":")
            claim_value, role = claim_value.strip(), role.strip().lower()
            if not sep or not claim_value or not role:
                raise ValueError(
                    f"oidc_role_map entry must be 'claimval:role': {entry!r}"
                )
            if claim_value in mapping:
                raise ValueError(f"duplicate claim value {claim_value!r} in oidc_role_map")
            mapping[claim_value] = role
        return mapping

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
