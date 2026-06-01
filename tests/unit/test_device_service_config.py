"""Unit: config + LLM_BASE_URL allowlist (FR-342)."""
import pytest

from device_service.config import (
    DEFAULT_ALLOWLIST, Settings, parse_allowlist, validate_base_url,
)


def _allow():
    return parse_allowlist(DEFAULT_ALLOWLIST)


def test_none_base_url_ok():
    validate_base_url(None, _allow())
    validate_base_url("", _allow())


def test_http_localhost_ok():
    validate_base_url("http://localhost:11434/v1", _allow())
    validate_base_url("http://127.0.0.1:8000", _allow())


def test_http_host_docker_internal_ok():
    # Ollama path (PRD §14) — local host over http is allowed
    validate_base_url("http://host.docker.internal:11434/v1", _allow())


def test_http_non_local_rejected():
    with pytest.raises(ValueError):
        validate_base_url("http://attacker.example/v1", _allow())


def test_https_in_allowlist_ok():
    validate_base_url("https://api.anthropic.com", _allow())


def test_https_not_in_allowlist_rejected():
    with pytest.raises(ValueError):
        validate_base_url("https://attacker.example/v1", _allow())


def test_unsupported_scheme_rejected():
    with pytest.raises(ValueError):
        validate_base_url("ftp://api.anthropic.com", _allow())


def test_parse_allowlist_normalises():
    al = parse_allowlist(" API.Anthropic.com , localhost , ")
    assert "api.anthropic.com" in al and "localhost" in al and "" not in al


def test_settings_defaults_to_mock():
    s = Settings(_env_file=None)
    assert s.llm_provider == "mock" and s.llm_model == "claude-haiku-4-5"


def test_settings_rejects_bad_base_url():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_base_url="https://attacker.example/v1")


def test_settings_accepts_allowlisted_base_url():
    s = Settings(_env_file=None, llm_base_url="https://api.anthropic.com")
    assert s.llm_base_url == "https://api.anthropic.com"