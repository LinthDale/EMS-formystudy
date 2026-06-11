"""Skeleton credential store: env-provisioned demo users (PRD-0005 FR-530 P1 stub).

Format (env/.env ONLY, never the TOML): BFF_AUTH_USERS="user:sha256hex:role,..."
- password is stored as a SHA-256 hex digest (no plaintext in env)
- verification is constant-time and burns the same hash work for unknown users
- replace with a real IdP / argon2 store before any multi-tenant production use
"""
from __future__ import annotations

import hashlib
import re
import secrets
from types import MappingProxyType
from typing import Mapping

from .roles import Role

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# digest of an unguessable value, compared against for unknown users (timing parity)
_DUMMY_DIGEST = hashlib.sha256(secrets.token_bytes(32)).hexdigest()


def parse_auth_users(raw: str) -> Mapping[str, tuple[str, Role]]:
    """Parse and validate the user table. Fail fast (ValueError) on any malformed
    record — a half-loaded auth table must never boot (fail closed)."""
    users: dict[str, tuple[str, Role]] = {}
    if not raw.strip():
        return MappingProxyType(users)  # empty table: nobody can log in
    for record in raw.split(","):
        record = record.strip()
        if not record:
            continue
        parts = record.split(":")
        if len(parts) != 3:
            raise ValueError("auth_users record must be 'username:sha256hex:role'")
        username, digest, role_raw = (p.strip() for p in parts)
        if not _USERNAME_RE.fullmatch(username):
            raise ValueError(f"invalid username in auth_users: {username!r}")
        if not _SHA256_RE.fullmatch(digest.lower()):
            raise ValueError(f"auth_users password for {username!r} must be a sha256 hex digest")
        try:
            role = Role(role_raw.lower())
        except ValueError as exc:
            raise ValueError(f"unknown role {role_raw!r} for user {username!r}") from exc
        if username in users:
            raise ValueError(f"duplicate user {username!r} in auth_users")
        users[username] = (digest.lower(), role)
    return MappingProxyType(users)


def verify(users: Mapping[str, tuple[str, Role]], username: str, password: str) -> Role | None:
    """Constant-time credential check. Returns the user's single role, or None."""
    presented = hashlib.sha256(password.encode("utf-8")).hexdigest()
    stored_digest, role = users.get(username, (_DUMMY_DIGEST, None))
    if secrets.compare_digest(presented, stored_digest) and role is not None:
        return role
    return None
