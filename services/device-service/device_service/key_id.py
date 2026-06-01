"""Audit key-id derivation (PRD-0003 §7.3a `created_by_key_id`, FR-345 / W-E).

The raw OPS key is NEVER persisted. The audit identity is HMAC-SHA256 of the key
under the rotating audit salt; the salt version is stored alongside (separate
column) so a salt rotation keeps audit lineage without exposing the key.
"""
from __future__ import annotations

import hashlib
import hmac


def hash_key_id(api_key: str, salt: str, salt_version: str) -> str:
    """HMAC-SHA256(key=salt, msg=api_key) -> 64-char hex. salt_version is recorded
    separately by the caller. Raises ValueError if the salt is empty (startup must
    enforce a non-empty AUDIT_HASH_SALT before any correction write)."""
    if not salt:
        raise ValueError("AUDIT_HASH_SALT must be set to derive created_by_key_id")
    if not api_key:  # fail-closed: never collapse anon/empty callers to one shared id
        raise ValueError("api_key must be non-empty to derive created_by_key_id")
    if not salt_version:  # audit lineage (FR-345) requires a recorded version
        raise ValueError("salt_version must be non-empty")
    return hmac.new(salt.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()
