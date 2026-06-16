"""OIDC Authorization-Code + PKCE routes (ADR-024 Phase-1).

Two browser-facing GET routes that bracket the IdP redirect round-trip:

- ``GET /api/auth/oidc/login`` -> 302 to the IdP authorize endpoint, with a
  freshly minted state / nonce / PKCE S256 challenge. The verifier/state/nonce
  are stashed server-side (short-TTL ``OidcStateManager``); only the challenge,
  state and nonce leave the BFF.
- ``GET /api/auth/oidc/callback?code=&state=`` -> verify state (CSRF /
  request-binding), exchange code + verifier at the token endpoint, validate the
  id-token (signature/iss/aud/exp/iat/nonce), map claims -> Role, then mint the
  SAME server-side session as local login (SessionManager unchanged, ADR-023)
  and redirect the browser to the SPA with the session cookie set.

These are GET (browser navigations, not fetch) so the Origin-CSRF middleware —
which only guards mutating methods — does not apply; the OIDC ``state`` value is
the CSRF defence for this flow. Failures fail closed: a generic error status,
never the IdP detail / tokens / verifier.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from ..oidc import OidcError
from ..security import issue_session_cookie

_log = logging.getLogger("bff.routes.oidc")

router = APIRouter(prefix="/api/auth/oidc", tags=["auth"])

# the authorization code an IdP returns is opaque; bound the length so a junk
# query string is rejected at the boundary rather than forwarded upstream.
_MAX_CODE_LEN = 2048
_MAX_STATE_LEN = 512


def _require_oidc(request: Request):
    """The OIDC client only exists when BFF_AUTH_MODE=oidc; otherwise the flow is
    not available (mirrors local mode's 503 for the unselected provider)."""
    client = getattr(request.app.state, "oidc_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="oidc auth not available")
    return client


@router.get("/login")
async def oidc_login(request: Request) -> RedirectResponse:
    """Start the login: 302 to the IdP authorize endpoint (PKCE S256)."""
    client = _require_oidc(request)
    try:
        authz = client.build_authorize_request()
    except OidcError as exc:
        # build_authorize_request itself does no I/O, but stay defensive.
        _log.error("oidc login could not be started: %s", exc.kind)
        raise HTTPException(status_code=502, detail="oidc login unavailable") from exc
    request.app.state.oidc_state_manager.issue(
        authz.state, authz.code_verifier, authz.nonce
    )
    # 302 GET redirect; no body, no cookie yet (the session is minted on callback)
    return RedirectResponse(authz.authorize_url, status_code=302)


@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str = Query(min_length=1, max_length=_MAX_CODE_LEN),
    state: str = Query(min_length=1, max_length=_MAX_STATE_LEN),
) -> RedirectResponse:
    """Finish the login: verify state, exchange code, validate id-token, map the
    role, mint the session, redirect to the SPA with the cookie set."""
    client = _require_oidc(request)
    settings = request.app.state.settings

    # state must match a live, single-use entry — unknown/expired => CSRF/replay.
    login_state = request.app.state.oidc_state_manager.consume(state)
    if login_state is None:
        raise HTTPException(status_code=401, detail="invalid or expired login state")

    try:
        id_token = await client.exchange_code(code, login_state.code_verifier)
        claims = await client.validate_id_token(id_token, login_state.nonce)
        role = client.map_role(claims)
    except OidcError as exc:
        # discovery/token transport failures => 502 (our config / the IdP);
        # validation/claims failures => 401 (this login is not trustworthy).
        status = 502 if exc.kind in ("discovery", "token") else 401
        raise HTTPException(status_code=status, detail="oidc login failed") from exc

    # subject identifies the authenticated user for the session record / audit.
    username = str(claims.get("sub") or "")
    if not username:
        raise HTTPException(status_code=401, detail="oidc login failed")

    session = await request.app.state.session_manager.create(username, role)
    # land the browser back on the SPA; the cookie is the only thing it carries.
    target = settings.oidc_post_login_redirect or "/"
    response = RedirectResponse(target, status_code=302)
    issue_session_cookie(response, session.id, settings)
    return response
