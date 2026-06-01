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
    assert s.llm_provider == "mock"


def test_settings_rejects_bad_base_url():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_base_url="https://attacker.example/v1")


def test_settings_accepts_allowlisted_base_url():
    s = Settings(_env_file=None, llm_base_url="https://api.anthropic.com")
    assert s.llm_base_url == "https://api.anthropic.com"

# --- code review regression (RED) ---

def test_credentials_in_base_url_rejected():
    """MEDIUM: userinfo in LLM_BASE_URL must be rejected (use LLM_API_KEY)."""
    with pytest.raises(ValueError):
        validate_base_url("https://user:pass@api.anthropic.com", _allow())


def test_llm_model_default_is_empty_for_factory_fallback():
    """HIGH: config must not default to an Anthropic model (breaks openai/local)."""
    s = Settings(_env_file=None)
    assert s.llm_model == ""

def test_llm_pricing_json_must_be_object():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_pricing_json="[1, 2]")    # valid JSON but an array
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_pricing_json="not json")
    s = Settings(_env_file=None, llm_pricing_json='{"m": [1.0, 2.0]}')
    assert s.llm_pricing_json == '{"m": [1.0, 2.0]}'
    assert Settings(_env_file=None).llm_pricing_json == ""       # empty default ok

def test_provider_defaults_and_subscriptions_in_settings():
    s = Settings(_env_file=None)
    assert s.llm_default_model_anthropic == "claude-haiku-4-5"
    assert s.llm_default_model_openai == "gpt-4o-mini"
    assert s.llm_default_model_local == "qwen2.5"
    assert s.llm_local_base_url == "http://host.docker.internal:11434/v1"
    assert s.mqtt_subscriptions == "ems/+/+/measurements,factory/sensor/+"
    # env override
    s2 = Settings(_env_file=None, mqtt_subscriptions="ems/+/+/measurements")
    assert s2.mqtt_subscriptions == "ems/+/+/measurements"

# --- TOML config file source (project_rules §19; precedence env > .env > toml > default) ---

def _write_toml(tmp_path, body):
    p = tmp_path / "ds.toml"
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_toml_file_overrides_code_defaults(tmp_path, monkeypatch):
    cfg = _write_toml(tmp_path, '[llm]\nllm_provider = "anthropic"\n[llm_tuning]\nllm_retries = 7\nllm_confidence_threshold = 0.75\n')
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", cfg)
    s = Settings(_env_file=None)
    assert s.llm_provider == "anthropic" and s.llm_retries == 7 and s.llm_confidence_threshold == 0.75
    # untouched key keeps code default
    assert s.llm_cache_max == 4096


def test_env_var_overrides_toml(tmp_path, monkeypatch):
    cfg = _write_toml(tmp_path, '[llm]\nllm_provider = "anthropic"\n')
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", cfg)
    monkeypatch.setenv("LLM_PROVIDER", "openai")   # env must win over toml
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai"


def test_missing_toml_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", str(tmp_path / "nope.toml"))
    s = Settings(_env_file=None)
    assert s.llm_provider == "mock" and s.llm_retries == 3


def test_committed_toml_mirrors_code_defaults(monkeypatch):
    """Drift guard: config/device-service.toml must equal Settings code defaults
    (the file is the documented default; tests assume they match)."""
    import tomllib
    from pathlib import Path

    from device_service.config import DEFAULT_CONFIG_FILE
    # locate repo config relative to this test file
    here = Path(__file__).resolve()
    candidates = [Path(DEFAULT_CONFIG_FILE), here.parents[2] / DEFAULT_CONFIG_FILE]
    toml_path = next((p for p in candidates if p.is_file()), None)
    if toml_path is None:
        import pytest
        pytest.skip("device-service.toml not found from test CWD")
    monkeypatch.delenv("DEVICE_SERVICE_CONFIG_FILE", raising=False)
    flat = {}
    for v in tomllib.loads(toml_path.read_text(encoding="utf-8")).values():
        flat.update(v if isinstance(v, dict) else {})
    fields = Settings.model_fields
    for key, val in flat.items():
        assert key in fields, f"toml key {key} not a Settings field"
        assert fields[key].default == val, f"toml {key}={val!r} != code default {fields[key].default!r}"
    # reverse direction: every non-secret, non-excluded Settings field must be in the TOML.
    # Secrets are derived from SECRET_FIELDS so the two can never drift.
    from device_service.config import SECRET_FIELDS
    excluded = set(SECRET_FIELDS) | {
        "llm_base_url",  # optional, commented out in TOML
    }
    for key in fields:
        if key not in excluded:
            assert key in flat, f"Settings field {key!r} missing from committed TOML"

def test_toml_source_flattens_and_get_field_value(tmp_path, monkeypatch):
    from device_service.config import Settings, TomlConfigSource
    # top-level key (no section) + a sectioned key -> both flattened
    cfg = tmp_path / "ds.toml"
    cfg.write_text('llm_retries = 9\n[llm]\nllm_provider = "openai"\n', encoding="utf-8")
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", str(cfg))
    src = TomlConfigSource(Settings)
    assert src()["llm_retries"] == 9 and src()["llm_provider"] == "openai"
    val, name, complex_ = src.get_field_value(Settings.model_fields["llm_provider"], "llm_provider")
    assert val == "openai" and name == "llm_provider" and complex_ is False

def test_toml_secret_keys_are_ignored(tmp_path, monkeypatch):
    """A secret accidentally placed in the TOML must NOT be loaded (footgun guard)."""
    cfg = tmp_path / "ds.toml"
    cfg.write_text('[db]\ndb_ai_password = "leaked-from-toml"\ndb_host = "toml-host"\n', encoding="utf-8")
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", str(cfg))
    s = Settings(_env_file=None)
    assert s.db_ai_password == ""          # secret ignored -> falls back to .env/default, NOT the toml value
    assert s.db_host == "toml-host"         # non-secret still loaded


def test_toml_duplicate_key_across_sections_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "ds.toml"
    cfg.write_text('[a]\nllm_retries = 1\n[b]\nllm_retries = 2\n', encoding="utf-8")
    monkeypatch.setenv("DEVICE_SERVICE_CONFIG_FILE", str(cfg))
    with pytest.raises(ValueError):
        Settings(_env_file=None)