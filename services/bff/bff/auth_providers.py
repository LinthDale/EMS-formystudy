"""Legacy pure provider adapters retained for compatibility tests.

Runtime local authentication uses accounts.AccountAuth and PostgreSQL (ADR-035).
These adapters do not read environment variables and are not selected by main.py.
OIDC routes continue to use the existing redirect/PKCE client.
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
    """OIDC / enterprise IdP provider — the strategic primary per ADR-024.

    OIDC authenticates via a browser redirect round-trip (Authorization-Code +
    PKCE), NOT a username/password POST. The real flow therefore lives in
    ``routes/oidc.py`` + ``oidc.py`` (discovery, redirect, token exchange,
    id-token validation, claim→role mapping); this provider only exists to keep
    the startup seam uniform.

    The password ``authenticate`` path is deliberately unavailable in OIDC mode:
    the BFF does not collect passwords for an external IdP. The password
    ``/api/auth/login`` route maps the resulting ``NotImplementedError`` to 503
    (fail closed — never a silent insecure fallback), pointing callers at
    ``GET /api/auth/oidc/login``.
    """

    mode = "oidc"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate(self, username: str, password: str) -> Role | None:
        raise NotImplementedError(
            "OIDC mode authenticates via GET /api/auth/oidc/login (redirect + "
            "PKCE), not username/password. Use the OIDC login route."
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
