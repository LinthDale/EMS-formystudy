"""argon2id local credential store + pluggable auth-provider seam (ADR-024).

Covers the fallback path that replaced the SHA-256 stub:
- argon2id verify accepts the right password and rejects the wrong one
- only argon2id PHC strings parse (argon2i / sha256-hex / junk are rejected)
- unknown users get a constant-work dummy verify (no enumeration shortcut)
- provider selection by BFF_AUTH_MODE; OIDC's password path is not used (the
  real OIDC flow is a browser redirect, ADR-024 — see test_oidc_flow.py)
"""
from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from bff import credentials
from bff.auth_providers import (
    LocalArgon2Provider,
    OidcProvider,
    build_auth_provider,
)
from bff.roles import Role
from tests import oidc_fixtures as mock
from tests.conftest import make_settings, phc

# ---------------------------------------------------------------- parse + verify


def test_parse_accepts_argon2id_phc_record():
    users = credentials.parse_auth_users(f"ops_user:{phc('ops-pw')}:ops")
    stored_hash, role = users["ops_user"]
    assert stored_hash.startswith("$argon2id$")
    assert role is Role.OPS


def test_verify_accepts_correct_password():
    users = credentials.parse_auth_users(f"ops_user:{phc('s3cret')}:ops")
    assert credentials.verify(users, "ops_user", "s3cret") is Role.OPS


def test_verify_rejects_wrong_password():
    users = credentials.parse_auth_users(f"ops_user:{phc('s3cret')}:ops")
    assert credentials.verify(users, "ops_user", "wrong") is None


def test_verify_rejects_unknown_user_via_dummy_hash():
    users = credentials.parse_auth_users(f"ops_user:{phc('s3cret')}:ops")
    # unknown user must return None (and internally runs a dummy verify)
    assert credentials.verify(users, "ghost", "anything") is None


# ---------------------------------------------------------------- PHC validation


def test_parse_rejects_sha256_hex_digest():
    """The old SHA-256 record format must no longer be accepted."""
    with pytest.raises(ValueError):
        credentials.parse_auth_users("ops_user:" + ("a" * 64) + ":ops")


def test_parse_rejects_argon2i_phc():
    """Only argon2id is accepted; argon2i (weaker here) is rejected."""
    argon2i = PasswordHasher().hash("x").replace("$argon2id$", "$argon2i$", 1)
    with pytest.raises(ValueError):
        credentials.parse_auth_users(f"ops_user:{argon2i}:ops")


def test_parse_rejects_record_without_hash():
    with pytest.raises(ValueError):
        credentials.parse_auth_users("ops_user:ops")  # only one ':'


def test_parse_rejects_unknown_role():
    with pytest.raises(ValueError):
        credentials.parse_auth_users(f"ops_user:{phc('x')}:superadmin")


def test_parse_rejects_duplicate_user():
    record = f"ops_user:{phc('a')}:ops;ops_user:{phc('b')}:ingest"
    with pytest.raises(ValueError):
        credentials.parse_auth_users(record)


def test_empty_table_is_fail_closed():
    users = credentials.parse_auth_users("")
    assert dict(users) == {}
    assert credentials.verify(users, "anyone", "anything") is None


# ---------------------------------------------------------------- provider seam


def test_build_provider_local_is_default():
    users = credentials.parse_auth_users(f"ops_user:{phc('pw')}:ops")
    provider = build_auth_provider(make_settings(), users)
    assert isinstance(provider, LocalArgon2Provider)
    assert provider.mode == "local"
    assert provider.authenticate("ops_user", "pw") is Role.OPS
    assert provider.authenticate("ops_user", "nope") is None


def test_build_provider_oidc_selected_by_mode():
    settings = make_settings(**mock.oidc_overrides())
    provider = build_auth_provider(settings, {})
    assert isinstance(provider, OidcProvider)
    assert provider.mode == "oidc"


def test_oidc_provider_password_path_raises_not_implemented():
    # OIDC authenticates via the redirect flow, not username/password; the
    # password path is deliberately unavailable (the route maps this to 503).
    provider = OidcProvider(make_settings(**mock.oidc_overrides()))
    with pytest.raises(NotImplementedError):
        provider.authenticate("user", "pw")


def test_unknown_auth_mode_rejected_at_config():
    """A typo in BFF_AUTH_MODE must fail fast, never silently disable auth."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make_settings(auth_mode="bogus")
