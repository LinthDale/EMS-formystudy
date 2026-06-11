"""Auth routes: login / logout / session info / role change.

Login is the ONLY place a session is minted; role changes never re-scope a
live session (any change revokes it — §9.1 [必過] downgrade rule, applied
strictly). All mutating routes here are additionally covered by the
Origin-CSRF middleware.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import credentials
from ..roles import Role
from ..security import clear_session_cookie, current_session, issue_session_cookie
from ..sessions import Session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RoleChangeRequest(BaseModel):
    role: Role


@router.post("/login")
async def login(body: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings
    role = credentials.verify(request.app.state.users, body.username, body.password)
    if role is None:
        # identical answer for unknown user / wrong password (no enumeration)
        raise HTTPException(status_code=401, detail="invalid credentials")
    session = await request.app.state.session_manager.create(body.username, role)
    response = JSONResponse(
        {"username": session.username, "role": session.role.value,
         "expires_in": settings.session_max_lifetime_s}
    )
    issue_session_cookie(response, session.id, settings)
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, session: Session = Depends(current_session)) -> Response:
    await request.app.state.session_manager.revoke(session.id)
    response = Response(status_code=204)
    clear_session_cookie(response, request.app.state.settings)
    return response


@router.get("/session")
async def session_info(session: Session = Depends(current_session)) -> dict:
    return {"username": session.username, "role": session.role.value}


@router.post("/role")
async def change_role(
    body: RoleChangeRequest, request: Request, session: Session = Depends(current_session)
) -> Response:
    """Role downgrade (or any change) terminates the session; the user must
    re-authenticate to obtain a session with different privileges (§9.1)."""
    terminated = await request.app.state.session_manager.change_role(session, body.role)
    response = JSONResponse(
        {"session_terminated": terminated,
         "role": (body.role if terminated else session.role).value}
    )
    if terminated:
        clear_session_cookie(response, request.app.state.settings)
    return response
