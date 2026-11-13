"""OIDC Authorization-Code + PKCE client (ADR-024, the strategic primary auth).

This module turns the ``OidcProvider`` seam ADR-024 left stubbed into a real
implementation. It owns everything between the BFF and the IdP; the routes
(``routes/oidc.py``) only orchestrate the redirect round-trip and then mint the
SAME server-side session as local login (SessionManager unchanged, ADR-023).

What lives here:
- discovery: fetch ``{issuer}/.well-known/openid-configuration`` and cache the
  authorize/token/jwks endpoints + the signing JWKS (httpx, already a dep);
- PKCE: generate ``code_verifier`` and the S256 ``code_challenge``;
- the authorize redirect URL (with state / nonce / challenge);
- token exchange: POST code + verifier to the token endpoint;
- id-token validation: JWKS signature, ``iss`` / ``aud`` / ``exp`` / ``iat`` /
  ``nonce`` — via authlib's JOSE claim validation;
- claim -> Role mapping: configurable claim + value->role map, fail closed.

Security invariants (PRD-0005 §9, ADR-024):
- the PKCE ``code_verifier``, ``client_secret`` and raw tokens are NEVER logged
  and NEVER returned to the browser;
- any validation failure raises ``OidcError`` with a generic, non-leaking
  message; the route maps it to a fail-closed HTTP status (401/502);
- an unmapped / empty role claim is rejected (no default privilege).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from .config import Settings
from .roles import Role

_log = logging.getLogger("bff.oidc")

# id-tokens from an OIDC IdP are RS/ES asymmetric-signed; pin the algorithm set
# so a forged token cannot downgrade to "alg": "none" or to an HMAC the JWKS
# public key would be mis-used as a secret for.
_ALLOWED_ID_TOKEN_ALGS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")
# small clock-skew leeway for exp/iat (IdP and BFF clocks are rarely identical)
_LEEWAY_S = 60


class OidcError(Exception):
    """Any OIDC failure that must NOT leak internals to the browser. Carries a
    coarse ``kind`` so the route can fail closed (discovery/upstream -> 502,
    everything else -> 401) without echoing the detail."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # "discovery" | "token" | "validation" | "claims"


@dataclass(frozen=True, slots=True)
class OidcAuthorizeRequest:
    """The data a login needs: where to send the browser, and the per-login
    secrets to stash server-side (verifier/state/nonce)."""

    authorize_url: str
    state: str
    nonce: str
    code_verifier: str


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256 (RFC 7636).

    The verifier is a high-entropy URL-safe secret; the challenge is its
    SHA-256, base64url without padding. Only the challenge ever leaves the BFF."""
    code_verifier = secrets.token_urlsafe(64)  # >= 43 chars, well within 128 max
    challenge = _b64url_no_pad(hashlib.sha256(code_verifier.encode("ascii")).digest())
    return code_verifier, challenge


def _validate_role_map(settings: Settings) -> dict[str, Role]:
    """Resolve the configured ``claimval:role`` csv into ``{value: Role}``.

    Fail fast on an unknown role string so a typo cannot silently drop a mapping
    (which would then reject a legitimate user)."""
    out: dict[str, Role] = {}
    for value, role_str in settings.oidc_role_mapping.items():
        try:
            out[value] = Role(role_str)
        except ValueError as exc:
            raise ValueError(
                f"oidc_role_map references unknown role {role_str!r}"
            ) from exc
    return out


class OidcClient:
    """Holds discovered metadata + cached JWKS and the validated role map.

    Construct via :meth:`discover` (async) so the network fetch is explicit. The
    instance is effectively immutable after discovery except for a lazily
    refreshed JWKS (rotation handling)."""

    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        *,
        authorize_endpoint: str,
        token_endpoint: str,
        jwks_uri: str,
        jwks,
        role_map: dict[str, Role],
        clock=time.time,
    ) -> None:
        self._settings = settings
        self._http = http
        self._authorize_endpoint = authorize_endpoint
        self._token_endpoint = token_endpoint
        self._jwks_uri = jwks_uri
        self._jwks = jwks
        self._role_map = role_map
        self._clock = clock
        self._jwt = JsonWebToken(_ALLOWED_ID_TOKEN_ALGS)

    @classmethod
    async def discover(
        cls, settings: Settings, http: httpx.AsyncClient, *, clock=time.time
    ) -> "OidcClient":
        """Fetch the discovery document + JWKS. Raises ``OidcError('discovery')``
        on any network / shape failure so the route can answer 502 (fail closed)."""
        role_map = _validate_role_map(settings)
        issuer = settings.oidc_issuer.rstrip("/")
        well_known = f"{issuer}/.well-known/openid-configuration"
        meta = await cls._get_json(http, well_known)
        try:
            authorize_endpoint = meta["authorization_endpoint"]
            token_endpoint = meta["token_endpoint"]
            jwks_uri = meta["jwks_uri"]
            # the IdP's self-declared issuer must match what we trust
            if meta.get("issuer", "").rstrip("/") != issuer:
                raise OidcError("discovery", "discovery issuer mismatch")
        except (KeyError, TypeError) as exc:
            raise OidcError("discovery", "discovery document malformed") from exc
        jwks_doc = await cls._get_json(http, jwks_uri)
        jwks = cls._import_jwks(jwks_doc)
        return cls(
            settings,
            http,
            authorize_endpoint=authorize_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
            jwks=jwks,
            role_map=role_map,
            clock=clock,
        )

    @staticmethod
    async def _get_json(http: httpx.AsyncClient, url: str) -> dict:
        try:
            resp = await http.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            # log the class only — never the URL/params (could carry hints)
            _log.error("OIDC discovery fetch failed: %s", type(exc).__name__)
            raise OidcError("discovery", "identity provider unreachable") from exc
        if resp.status_code != 200:
            _log.error("OIDC discovery fetch HTTP %d", resp.status_code)
            raise OidcError("discovery", "identity provider error")
        try:
            return resp.json()
        except ValueError as exc:
            raise OidcError("discovery", "identity provider returned non-JSON") from exc

    @staticmethod
    def _import_jwks(jwks_doc: dict):
        try:
            return JsonWebKey.import_key_set(jwks_doc)
        except (JoseError, ValueError, KeyError, TypeError) as exc:
            raise OidcError("discovery", "identity provider JWKS malformed") from exc

    def build_authorize_request(self) -> OidcAuthorizeRequest:
        """Mint per-login state/nonce/PKCE and the authorize redirect URL.

        ``state`` and ``nonce`` are independent high-entropy values so neither
        can be derived from the other. The verifier is returned for server-side
        stashing; only the S256 challenge is placed in the URL."""
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier, code_challenge = generate_pkce_pair()
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": self._settings.oidc_redirect_uri,
            "scope": " ".join(self._settings.oidc_scope_list),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        url = str(httpx.URL(self._authorize_endpoint, params=params))
        return OidcAuthorizeRequest(
            authorize_url=url,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )

    async def exchange_code(self, code: str, code_verifier: str) -> str:
        """Exchange an authorization code (+ PKCE verifier) for the id-token.

        Returns the raw id-token JWS (validated later). Raises
        ``OidcError('token')`` on any token-endpoint failure. The client secret
        and code are sent in the POST body only — never logged."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.oidc_redirect_uri,
            "client_id": self._settings.oidc_client_id,
            "code_verifier": code_verifier,
        }
        if self._settings.oidc_client_secret:
            data["client_secret"] = self._settings.oidc_client_secret
        try:
            resp = await self._http.post(
                self._token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            _log.error("OIDC token exchange failed: %s", type(exc).__name__)
            raise OidcError("token", "token endpoint unreachable") from exc
        if resp.status_code != 200:
            _log.error("OIDC token endpoint HTTP %d", resp.status_code)
            raise OidcError("token", "token exchange rejected")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise OidcError("token", "token endpoint returned non-JSON") from exc
        id_token = payload.get("id_token")
        if not id_token or not isinstance(id_token, str):
            raise OidcError("token", "token response missing id_token")
        return id_token

    async def _refresh_jwks(self) -> None:
        """Re-fetch the JWKS (key rotation): a kid we have not seen yet means the
        IdP rotated its signing key since discovery."""
        jwks_doc = await self._get_json(self._http, self._jwks_uri)
        self._jwks = self._import_jwks(jwks_doc)

    def _decode_and_validate(self, id_token: str, nonce: str) -> dict:
        """Verify signature against the cached JWKS and validate the registered
        claims (iss/aud/exp/iat) plus nonce. Raises ``OidcError('validation')``."""
        claims_options = {
            "iss": {"essential": True, "value": self._settings.oidc_issuer.rstrip("/")},
            "aud": {"essential": True, "value": self._settings.oidc_client_id},
            "exp": {"essential": True},
            "iat": {"essential": True},
        }
        try:
            claims = self._jwt.decode(
                id_token,
                key=self._jwks,
                claims_options=claims_options,
            )
            claims.validate(now=int(self._clock()), leeway=_LEEWAY_S)
        except (JoseError, ValueError, KeyError) as exc:
            # JoseError covers bad signature / wrong iss/aud / expired / bad alg;
            # ValueError/KeyError cover a signing `kid` that is not in the JWKS
            # (authlib raises a bare ValueError there) — i.e. a rotated or forged
            # key. All map to a fail-closed validation error (401 at the route).
            _log.warning("OIDC id-token validation failed: %s", type(exc).__name__)
            raise OidcError("validation", "id-token validation failed") from exc
        # nonce is an OIDC (not registered JWT) claim — validate explicitly and
        # in constant relevance: a missing or mismatched nonce is a replay.
        token_nonce = claims.get("nonce")
        if not token_nonce or not secrets.compare_digest(str(token_nonce), nonce):
            _log.warning("OIDC id-token nonce mismatch")
            raise OidcError("validation", "id-token nonce mismatch")
        return dict(claims)

    async def validate_id_token(self, id_token: str, nonce: str) -> dict:
        """Validate the id-token, transparently refreshing the JWKS once if the
        signing ``kid`` is unknown (key rotation). Returns the claim set."""
        try:
            return self._decode_and_validate(id_token, nonce)
        except OidcError as first:
            if first.kind != "validation":
                raise
            # one retry after a JWKS refresh handles rotation; if it still fails,
            # surface the original failure (do not loop / hammer the IdP).
            try:
                await self._refresh_jwks()
            except OidcError:
                raise first
            return self._decode_and_validate(id_token, nonce)

    def map_role(self, claims: dict) -> Role:
        """Map the configured role claim's value(s) -> Role (fail closed).

        The claim may be a single string or a list (e.g. ``groups``). The FIRST
        value that maps wins. An empty/absent claim, or no value mapping to a
        known role, is rejected (no default privilege). Raises
        ``OidcError('claims')``."""
        raw = claims.get(self._settings.oidc_role_claim)
        values: list[str]
        if raw is None:
            values = []
        elif isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, (list, tuple)):
            values = [str(v) for v in raw]
        else:
            values = [str(raw)]
        for value in values:
            role = self._role_map.get(value)
            if role is not None:
                return role
        _log.warning(
            "OIDC role claim %r mapped to no known role (rejecting, fail closed)",
            self._settings.oidc_role_claim,
        )
        raise OidcError("claims", "no permitted role for this account")
