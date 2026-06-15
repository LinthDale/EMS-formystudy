"""Pluggable authentication provider seam (ADR-024).

Owner decision (2026-06-15): the BFF stops self-managing passwords. Enterprise
IdP / OIDC is the strategic, long-term primary; a local argon2id user table is
the fallback for environments with no IdP yet.

To keep that direction without coupling routes to a concrete mechanism, login
goes through an ``AuthProvider`` selected by ``BFF_AUTH_MODE``:

- ``local`` (default, implemented now): ``LocalArgon2Provider`` over the
  argon2id ``BFF_AUTH_USERS`` table (see ``credentials.py``).
- ``oidc`` (interface only — Phase-1): ``OidcProvider`` raises a clear
  ``NotImplementedError`` until a real IdP integration lands. No IdP exists to
  integrate against yet, so the full Authorization-Code + PKCE flow is
  deliberately deferred; the seam exists so adding it touches only this module.

Everything downstream of authentication (session minting, CSRF, role→channel-key
mapping) is unchanged: a provider's only job is ``username/password -> Role | None``.
"""
from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from . import credentials
from .config import Settings
from .roles import Role


@runtime_checkable
class AuthProvider(Protocol):
    """Authenticate a credential and resolve the caller's single role.

    Returns the ``Role`` on success, or ``None`` on any authentication failure
    (unknown user / bad password / rejected assertion). Implementations MUST NOT
    leak which of those happened (no user enumeration) and MUST NOT log secrets.
    """

    mode: str

    def authenticate(self, username: str, password: str) -> Role | None: ...


class LocalArgon2Provider:
    """Fallback provider: verify against the local argon2id user table.

    Holds the parsed (immutable) user table; delegates the constant-work verify
    to ``credentials.verify`` so the enumeration-resistance guarantees live in
    one place.
    """

    mode = "local"

    def __init__(self, users: Mapping[str, tuple[str, Role]]) -> None:
        self._users = users

    def authenticate(self, username: str, password: str) -> Role | None:
        return credentials.verify(self._users, username, password)


class OidcProvider:
    """OIDC / enterprise IdP provider — interface only, deferred to Phase-1.

    The strategic primary per ADR-024. The full Authorization-Code + PKCE flow
    (discovery, redirect, token exchange, id-token validation, claim→role
    mapping) is intentionally NOT implemented in P1 because there is no IdP to
    integrate against yet. Selecting ``BFF_AUTH_MODE=oidc`` fails loudly rather
    than silently degrading to an insecure path (fail closed).
    """

    mode = "oidc"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate(self, username: str, password: str) -> Role | None:
        raise NotImplementedError(
            "OIDC auth provider is not implemented in Phase-1 (ADR-024): "
            "no enterprise IdP is integrated yet. Use BFF_AUTH_MODE=local."
        )


def build_auth_provider(
    settings: Settings, users: Mapping[str, tuple[str, Role]]
) -> AuthProvider:
    """Select the auth provider by config (``BFF_AUTH_MODE``). Fail fast on an
    unknown mode so a typo can never silently disable authentication."""
    mode = settings.auth_mode.strip().lower()
    if mode == "local":
        return LocalArgon2Provider(users)
    if mode == "oidc":
        return OidcProvider(settings)
    raise ValueError(
        f"unknown BFF_AUTH_MODE {settings.auth_mode!r} (expected 'local' or 'oidc')"
    )
