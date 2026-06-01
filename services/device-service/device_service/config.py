"""Runtime configuration (pydantic-settings) + LLM_BASE_URL allowlist (FR-342).

Env (no prefix): LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL,
LLM_PROVIDER_DOMAIN_ALLOWLIST, DB_HOST, DB_PORT, DB_NAME, DB_AI_PASSWORD,
DB_OPS_PASSWORD, OPS_API_KEY, INGEST_API_KEY, AI_API_KEY.
"""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        validate_base_url(self.llm_base_url, self.allowlist)
        return self