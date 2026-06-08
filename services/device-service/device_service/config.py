"""Runtime configuration (pydantic-settings).

Single human-editable tunable file: config/device-service.toml (annotated). Load
precedence (high -> low): env vars > .env > TOML file > code defaults. Secrets
(DB_*_PASSWORD, *_API_KEY, LLM_API_KEY) live in .env only, never in the TOML.
TOML path overridable via DEVICE_SERVICE_CONFIG_FILE. See project_rules §19 and
doc/governance/tunable-parameters.md.
"""
from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_cfg_log = logging.getLogger("device_service.config")
DEFAULT_CONFIG_FILE = "config/device-service.toml"
# secrets must come from env/.env only; ignored if present in the (committed) TOML
SECRET_FIELDS = frozenset({
    "llm_api_key", "guardrail_api_key", "db_ai_password", "db_ops_password",
    "ops_api_key", "ingest_api_key", "ai_api_key", "audit_hash_salt",
})


class TomlConfigSource(PydanticBaseSettingsSource):
    """Loads tunables from an annotated TOML file (flattened one level of [tables]).
    Missing file -> empty (code defaults apply). Path: DEVICE_SERVICE_CONFIG_FILE
    or config/device-service.toml relative to CWD."""

    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        self._data = self._load()

    @staticmethod
    def _load() -> dict:
        path = Path(os.getenv("DEVICE_SERVICE_CONFIG_FILE", DEFAULT_CONFIG_FILE))
        if not path.is_file():
            _cfg_log.info("TOML config not found at %s - using code defaults", path)
            return {}
        with path.open("rb") as fh:
            raw = tomllib.load(fh)   # malformed TOML -> TOMLDecodeError (fail fast at startup)
        flat: dict = {}

        def _put(key, value):
            if key in SECRET_FIELDS:                 # never load secrets from the (committed) TOML
                _cfg_log.warning("ignoring secret-like key %r in TOML; set it via .env instead", key)
                return
            if key in flat:                          # same key under two [sections]
                raise ValueError(f"TOML key {key!r} appears in multiple sections")
            flat[key] = value

        for key, value in raw.items():
            if isinstance(value, dict):              # [section] table -> flatten its keys
                for k, v in value.items():
                    _put(k, v)
            else:
                _put(key, value)
        _cfg_log.info("loaded TOML config from %s (%d keys)", path, len(flat))
        return flat

    def get_field_value(self, field: FieldInfo, field_name: str):
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict:
        return {k: v for k, v in self._data.items()}

# http:// is only accepted for these local hosts (covers Ollama via host.docker.internal,
# per PRD §14); everything else over http is rejected (FR-342 rule a).
LOCAL_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
DEFAULT_ALLOWLIST = "api.anthropic.com,api.openai.com,localhost,127.0.0.1,host.docker.internal"


def parse_allowlist(raw: str) -> frozenset[str]:
    return frozenset(h.strip().lower() for h in (raw or "").split(",") if h.strip())


def validate_base_url(base_url: str | None, allowlist: frozenset[str]) -> None:
    """Raise ValueError if base_url violates FR-342. None/empty is allowed (provider default)."""
    if not base_url:
        return
    parsed = urlparse(base_url)
    if parsed.username or parsed.password:
        raise ValueError("LLM_BASE_URL: credentials (user:pass@) must not be embedded; use LLM_API_KEY")
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()  # note: "::1" only matches RFC 2732 bracketed form [::1]
    if scheme == "http":
        if host not in LOCAL_HTTP_HOSTS:
            raise ValueError(f"LLM_BASE_URL: http:// only allowed for local hosts, got {base_url!r}")
        return
    if scheme == "https":
        if host not in allowlist:
            raise ValueError(
                f"LLM_BASE_URL: https host {host!r} not in LLM_PROVIDER_DOMAIN_ALLOWLIST "
                f"(extend the allowlist to accept it)"
            )
        return
    raise ValueError(f"LLM_BASE_URL: unsupported scheme in {base_url!r} (use http/https)")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # LLM
    llm_provider: str = "mock"
    llm_model: str = ""  # blank -> factory applies per-provider default
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_provider_domain_allowlist: str = DEFAULT_ALLOWLIST

    # L2 guardrail (FR-338, §8.7.3): independent provider/model/key from L1.
    # Default 'mock' keeps the deterministic guardrail (no behaviour change, no LLM cost).
    # NOTE: a real guardrail provider's L2 token cost is NOT yet budget-metered (FR-340 follow-up)
    # -> L2 cost is UNCAPPED when enabled; main.py warns at startup.
    guardrail_provider: str = "mock"
    guardrail_model: str = ""               # blank -> factory per-provider default
    guardrail_api_key: str = ""             # blank -> reuse llm_api_key (§8.7.3)
    guardrail_base_url: str | None = None
    guardrail_default_model_openai: str = "gpt-4o-mini"  # cheapest model adequate for injection judging
    guardrail_max_output_tokens: int = 256  # L2 verdict JSON is small; keep the call cheap

    # LLM tuning (single source; project_rules §19 / tunable-parameters.md)
    llm_max_output_tokens: int = 1024       # provider max_tokens AND budget reservation output bound (COUPLED)
    llm_reserve_input_tokens: int = 4000    # budget reservation input estimate
    llm_confidence_threshold: float = 0.9   # FR-303: > this -> auto confirmed
    llm_retries: int = 3                    # FR-312
    llm_cache_max: int = 4096               # FR-316 classifier cache size
    llm_pricing_json: str = ""            # optional JSON {model: [in_per_1M, out_per_1M]} merged onto defaults
    budget_warn_ratio: float = 0.8          # FR-319
    # discovery admission (FR-325/326) + transport
    dedupe_window_s: float = 60.0
    rate_limit_per_min: int = 60
    rate_window_s: float = 60.0
    mqtt_reconnect_delay_s: float = 5.0
    mqtt_subscriptions: str = "ems/+/+/measurements,factory/sensor/+"  # comma-separated MQTT topics
    # per-provider default model + local endpoint (single source; factory reads these)
    llm_default_model_anthropic: str = "claude-haiku-4-5"
    llm_default_model_openai: str = "gpt-4o-mini"
    llm_default_model_local: str = "qwen2.5"
    llm_local_base_url: str = "http://host.docker.internal:11434/v1"

    # DB (ADR-017 dual pools; per-role login)
    db_host: str = "timescaledb"
    db_port: int = 5432
    db_name: str = "ems"
    db_ai_password: str = ""
    db_ops_password: str = ""

    # X-API-Key channels (FR-310)
    ops_api_key: str = ""
    ingest_api_key: str = ""
    ai_api_key: str = ""

    # audit identity for human corrections (§7.3a / FR-345); salt is a SECRET (.env only),
    # version is non-secret and recorded alongside created_by_key_id for rotation lineage.
    audit_hash_salt: str = ""
    audit_salt_version: str = "v1"

    # MQTT auto-discovery (Phase 1.3)
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_enabled: bool = False
    llm_monthly_budget_usd: float = 20.0

    @property
    def allowlist(self) -> frozenset[str]:
        return parse_allowlist(self.llm_provider_domain_allowlist)

    @field_validator("llm_pricing_json")
    @classmethod
    def _check_pricing_json(cls, v: str) -> str:
        if not v:
            return v
        import json
        try:
            parsed = json.loads(v)
        except ValueError as exc:
            raise ValueError(f"LLM_PRICING_JSON must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("LLM_PRICING_JSON must be a JSON object {model: [in_per_1M, out_per_1M]}")
        return v

    @model_validator(mode="after")
    def _check_base_url(self) -> "Settings":
        validate_base_url(self.llm_base_url, self.allowlist)        # FR-342
        validate_base_url(self.guardrail_base_url, self.allowlist)  # FR-342 (L2 same rule)
        return self

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings,
    ):
        # precedence high -> low: init (kwargs) > env > .env > TOML > code defaults
        return (init_settings, env_settings, dotenv_settings,
                TomlConfigSource(settings_cls), file_secret_settings)