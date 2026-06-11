"""Request-side security: session cookie, per-request validation, endpoint-level
role authz (PRD-0005 §9.1) and CSRF origin enforcement (§9.4, GATE-1 decision:
SameSite=Strict cookie + Origin-header allowlist on every mutating /api route).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import Settings
from .roles import Role
from .sessions import Session

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def issue_session_cookie(response: Response, session_id: str, settings: Settings) -> None:
    """§9.2 [必過]: HttpOnly; Secure; SameSite=Strict — nothing readable by JS,
    nothing in localStorage/sessionStorage, opaque value only."""
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_max_lifetime_s,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )


async def current_session(request: Request) -> Session:
    """Validate the session on EVERY request — before any key material is
    selected or any upstream is contacted (§9.2 [必過])."""
    settings: Settings = request.app.state.settings
    session_id = request.cookies.get(settings.session_cookie_name)
    session = await request.app.state.session_manager.validate(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return session


def require_roles(*allowed: Role):
    """Endpoint-level authz (§9.1 [必過]): the route declares which roles may
    use it; everything else is 403 even though the BFF process holds the keys."""

    async def _dep(session: Session = Depends(current_session)) -> Session:
        if session.role not in allowed:
            raise HTTPException(status_code=403, detail="role not permitted for this endpoint")
        return session

    return Depends(_dep)


class OriginCSRFMiddleware(BaseHTTPMiddleware):
    """Deny-by-default CSRF gate: every mutating method under /api must present
    an Origin header matching the configured public origin allowlist. Runs
    before routing so future mutating routes are covered automatically.
    Also stamps defensive response headers on all /api responses."""

    def __init__(self, app, allowed_origins: frozenset[str]):
        super().__init__(app)
        self._allowed = allowed_origins

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin")
            if origin is None or origin not in self._allowed:
                response: Response = JSONResponse(
                    status_code=403, content={"detail": "origin check failed"}
                )
                return _stamp(response)
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            _stamp(response)
        return response


def _stamp(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
