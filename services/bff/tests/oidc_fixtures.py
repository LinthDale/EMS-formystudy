"""In-process mock OIDC issuer for BFF OIDC tests (ADR-024).

The full login -> callback -> session flow is exercised WITHOUT a real IdP by:

- generating an RSA keypair in-process and publishing the public half as a JWKS;
- serving ``/.well-known/openid-configuration`` + ``/jwks`` + ``/token`` through
  the same ``httpx.MockTransport`` boundary the rest of the BFF tests use, so the
  BFF's real httpx client talks to this fake over the transport seam (no network);
- signing id-tokens with RS256 so the BFF's JWKS-signature path runs for real.

Helpers let a test mint tokens with deliberately wrong aud/iss, expired times,
or a bad signature (a second, unpublished key) to cover the negative cases.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx
from authlib.jose import JsonWebKey, jwt

ISSUER = "https://idp.example.test"
CLIENT_ID = "ems-bff-client"
CLIENT_SECRET = "test-client-secret"
REDIRECT_URI = "https://testserver/api/auth/oidc/callback"
AUTHORIZE_ENDPOINT = f"{ISSUER}/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/token"
JWKS_URI = f"{ISSUER}/jwks"

# the auth code the mock issuer hands back at the (skipped) authorize step; the
# token endpoint accepts it and returns whatever id-token the test queued.
AUTH_CODE = "mock-authorization-code"


def _new_rsa_jwk(kid: str):
    """Generate an RSA private JWK (authlib) with the given kid."""
    key = JsonWebKey.generate_key("RSA", 2048, {"kid": kid, "use": "sig"}, is_private=True)
    return key


@dataclass
class MockIssuer:
    """A signing IdP behind an httpx.MockTransport handler.

    ``queued_id_token`` is returned by the token endpoint on the next exchange;
    tests set it via :meth:`make_id_token` / :meth:`queue`. ``token_status`` lets
    a test force a token-endpoint failure (502 path)."""

    issuer: str = ISSUER
    client_id: str = CLIENT_ID
    kid: str = "test-key-1"
    queued_id_token: str | None = None
    token_status: int = 200
    discovery_status: int = 200
    requests: list[httpx.Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._signing_key = _new_rsa_jwk(self.kid)
        # a second key NOT published in the JWKS -> "bad signature" cases sign
        # with this so the public set cannot verify them.
        self._rogue_key = _new_rsa_jwk("rogue-key")

    # ---- token minting -------------------------------------------------------
    def make_id_token(
        self,
        *,
        nonce: str,
        sub: str = "user-123",
        aud: str | None = None,
        iss: str | None = None,
        groups=("ems-ops",),
        exp_delta: int = 600,
        iat_delta: int = 0,
        sign_with_rogue: bool = False,
        extra: dict | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss if iss is not None else self.issuer,
            "aud": aud if aud is not None else self.client_id,
            "sub": sub,
            "exp": now + exp_delta,
            "iat": now + iat_delta,
            "nonce": nonce,
        }
        if groups is not None:
            claims["groups"] = list(groups)
        if extra:
            claims.update(extra)
        key = self._rogue_key if sign_with_rogue else self._signing_key
        header = {"alg": "RS256", "kid": key.kid}
        token = jwt.encode(header, claims, key)
        return token.decode("ascii") if isinstance(token, bytes) else token

    def queue(self, id_token: str) -> None:
        self.queued_id_token = id_token

    def rotate_signing_key(self, kid: str = "test-key-2") -> None:
        """Simulate IdP key rotation: switch to a fresh signing key whose kid the
        BFF's cached JWKS does not yet know (forces a JWKS refresh on verify)."""
        self.kid = kid
        self._signing_key = _new_rsa_jwk(kid)

    def public_jwks(self) -> dict:
        return {"keys": [self._signing_key.as_dict(is_private=False)]}

    # ---- transport handler ---------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            if self.discovery_status != 200:
                return httpx.Response(self.discovery_status, json={"error": "down"})
            return httpx.Response(200, json={
                "issuer": self.issuer,
                "authorization_endpoint": AUTHORIZE_ENDPOINT,
                "token_endpoint": TOKEN_ENDPOINT,
                "jwks_uri": JWKS_URI,
            })
        if path == "/jwks":
            return httpx.Response(200, json=self.public_jwks())
        if path == "/token" and request.method == "POST":
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            if self.queued_id_token is None:
                return httpx.Response(400, json={"error": "no token queued"})
            return httpx.Response(200, json={
                "access_token": "mock-access-token",
                "token_type": "Bearer",
                "id_token": self.queued_id_token,
            })
        return httpx.Response(404, json={"error": "not found", "path": path})


def oidc_overrides() -> dict:
    """Settings overrides that switch make_settings() into a valid oidc config."""
    return dict(
        auth_mode="oidc",
        oidc_issuer=ISSUER,
        oidc_client_id=CLIENT_ID,
        oidc_client_secret=CLIENT_SECRET,
        oidc_redirect_uri=REDIRECT_URI,
        oidc_role_claim="groups",
        # ems-ops -> ops, ems-ingest -> ingest, ems-view -> readonly
        oidc_role_map="ems-ops:ops,ems-ingest:ingest,ems-view:readonly",
        oidc_post_login_redirect="/app",
    )


def token_request_form(request: httpx.Request) -> dict:
    """Decode a urlencoded token-endpoint POST body into a flat dict for asserts."""
    parsed = parse_qs(request.content.decode("utf-8"))
    return {k: v[0] for k, v in parsed.items()}
