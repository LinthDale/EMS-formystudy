"""Local credential store: env-provisioned users hashed with argon2id.

Owner decision (2026-06-15, ADR-024): the BFF does NOT manage passwords long
term — enterprise IdP / OIDC is the strategic primary (deferred to Phase-1).
This module is the **local argon2id fallback** (`BFF_AUTH_MODE=local`, default),
replacing the earlier SHA-256 stub and closing the credential-hashing finding.

Format (env/.env ONLY, never the committed TOML); records are ``;``-separated:
    BFF_AUTH_USERS="username:<argon2id PHC string>:role;..."

- Records are separated by ``;`` (NOT ``,``): an argon2id PHC string contains a
  comma inside its params segment (``m=65536,t=3,p=4``), so comma cannot be the
  record separator. ``;`` never appears in a PHC string.
- The PHC string (e.g. ``$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>``) embeds
  the algorithm id, version, cost params and salt — no separate salt column.
- Only argon2id PHC strings are accepted; argon2i / argon2d (weaker for this
  use case) are rejected at parse time (fail fast).
- Verification uses argon2's own verify and burns the same hash work for unknown
  users (dummy verify) so login timing does not leak account existence.
- Empty table -> nobody can log in (fail closed).
- Generate hashes for the env var with: ``python -m bff.hashpw``.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Mapping

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .roles import Role

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
# argon2id PHC only: reject argon2i / argon2d which are weaker for this use case.
_ARGON2ID_PREFIX = "$argon2id$"

# Single shared hasher: argon2-cffi PasswordHasher is safe to reuse. Defaults are
# OWASP-aligned (m>=64MiB, t>=3, p>=4). Per-record params live inside each PHC
# string, so ops can re-tune via bff.hashpw without touching this module.
_HASHER = PasswordHasher()

# A real argon2id hash of an unguessable value; verifying against it for unknown
# users burns comparable CPU so login timing does not leak account existence.
_DUMMY_HASH = _HASHER.hash("\x00unguessable-dummy-secret\x00")


def _looks_like_argon2id(phc: str) -> bool:
    """True only for an argon2id PHC string with the expected segment count.

    A full argon2id PHC has the form
        $argon2id$v=<ver>$m=<m>,t=<t>,p=<p>$<b64salt>$<b64hash>
    i.e. 6 ``$``-delimited fields (leading empty field included).
    """
    if not phc.startswith(_ARGON2ID_PREFIX):
        return False
    # split on '$' -> ['', 'argon2id', 'v=19', 'm=..,t=..,p=..', salt, hash]
    return len(phc.split("$")) == 6


def parse_auth_users(raw: str) -> Mapping[str, tuple[str, Role]]:
    """Parse and validate the user table. Fail fast (ValueError) on any malformed
    record — a half-loaded auth table must never boot (fail closed).

    Each record is split on its FIRST and LAST ``:`` only: the username and role
    never contain ``:`` (enforced below) and an argon2id PHC string uses ``$`` as
    its internal separator, so the middle segment is the hash verbatim.
    """
    users: dict[str, tuple[str, Role]] = {}
    if not raw.strip():
        return MappingProxyType(users)  # empty table: nobody can log in
    for record in raw.split(";"):
        record = record.strip()
        if not record:
            continue
        first = record.find(":")
        last = record.rfind(":")
        if first == -1 or first == last:
            raise ValueError(
                "auth_users record must be 'username:<argon2id PHC>:role'"
            )
        username = record[:first].strip()
        phc = record[first + 1 : last].strip()
        role_raw = record[last + 1 :].strip()
        if not _USERNAME_RE.fullmatch(username):
            raise ValueError(f"invalid username in auth_users: {username!r}")
        if not _looks_like_argon2id(phc):
            raise ValueError(
                f"auth_users password for {username!r} must be an argon2id PHC string"
            )
        try:
            role = Role(role_raw.lower())
        except ValueError as exc:
            raise ValueError(f"unknown role {role_raw!r} for user {username!r}") from exc
        if username in users:
            raise ValueError(f"duplicate user {username!r} in auth_users")
        users[username] = (phc, role)
    return MappingProxyType(users)


def verify(
    users: Mapping[str, tuple[str, Role]], username: str, password: str
) -> Role | None:
    """Credential check via argon2id. Returns the user's single role, or None.

    For unknown users we still verify against a dummy hash so the response time
    does not reveal whether the username exists (enumeration resistance)."""
    stored = users.get(username)
    phc, role = (stored[0], stored[1]) if stored is not None else (_DUMMY_HASH, None)
    try:
        _HASHER.verify(phc, password)
    except (VerifyMismatchError, InvalidHashError):
        return None
    return role
