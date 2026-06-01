"""Runtime configuration (pydantic-settings) + LLM_BASE_URL allowlist (FR-342).

Env vars (no prefix): LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL,
LLM_PROVIDER_DOMAIN_ALLOWLIST.
"""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import model_validator
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

    llm_provider: str = "mock"
    llm_model: str = ""  # blank -> factory applies per-provider default
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_provider_domain_allowlist: str = DEFAULT_ALLOWLIST

    @property
    def allowlist(self) -> frozenset[str]:
        return parse_allowlist(self.llm_provider_domain_allowlist)

    @model_validator(mode="after")
    def _check_base_url(self) -> "Settings":
        validate_base_url(self.llm_base_url, self.allowlist)
        return self