"""Device proxy routes -> device-service REST :8002 (the secure template).

Representative of the PRD-0005 §8.1 pattern, NOT every FR:
- GET  /api/devices                      privileged list (OPS role -> OPS key)
- POST /api/devices/{id}/confirm         mutating OPS workflow action

Boundary rules: query params are deny-by-default allowlisted and re-validated
here (mirroring the device-service contract, openapi 1.3.0); device_id is
checked against the spec-locked FR-322 regex BEFORE anything goes upstream.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import Response

from ..roles import Role, channel_key_for
from ..security import require_roles
from ..sessions import Session
from ..upstream import forward

router = APIRouter(prefix="/api/devices", tags=["devices"])

DEVICE_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"  # FR-322, spec-locked
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SORT_FIELDS = frozenset({
    "device_id", "device_type", "status", "ai_confidence",
    "created_at", "updated_at", "last_seen_at",
})
_LIST_PARAMS = frozenset({"status", "type", "stale", "limit", "offset", "sort", "order"})


def _validated_list_params(request: Request) -> dict[str, str]:
    """Allowlist + re-validate every query param; unknown names fail fast (422)."""
    out: dict[str, str] = {}
    for name, value in request.query_params.multi_items():
        if name not in _LIST_PARAMS:
            raise HTTPException(status_code=422, detail=f"unknown query parameter: {name}")
        if name in out:
            raise HTTPException(status_code=422, detail=f"duplicate query parameter: {name}")
        if name in ("status", "type") and not _NAME_RE.fullmatch(value):
            raise HTTPException(status_code=422, detail=f"invalid value for {name}")
        if name == "stale" and value not in ("true", "false"):
            raise HTTPException(status_code=422, detail="stale must be true or false")
        if name == "limit" and not (value.isdigit() and 1 <= int(value) <= 500):
            raise HTTPException(status_code=422, detail="limit must be 1..500")
        if name == "offset" and not (value.isdigit() and int(value) <= 1_000_000):
            raise HTTPException(status_code=422, detail="offset must be a non-negative integer")
        if name == "sort" and value not in _SORT_FIELDS:
            raise HTTPException(status_code=422, detail="unsupported sort field")
        if name == "order" and value not in ("asc", "desc"):
            raise HTTPException(status_code=422, detail="order must be asc or desc")
        out[name] = value
    return out


def _key_or_503(role: Role, request: Request) -> str:
    key = channel_key_for(role, request.app.state.settings)
    if key is None:  # fail closed — never borrow another role's channel
        raise HTTPException(status_code=503, detail="channel key not configured")
    return key


@router.get("")
async def list_devices(
    request: Request, session: Session = require_roles(Role.OPS)
) -> Response:
    """FR-500 privileged list (candidate/retired/ai_confidence need the OPS channel)."""
    params = _validated_list_params(request)
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "GET",
        f"{settings.device_service_url}/devices",
        params=params,
        api_key=_key_or_503(session.role, request),
    )


@router.post("/{device_id}/confirm")
async def confirm_device(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-512 mutating OPS action (CSRF enforced by the origin middleware)."""
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "POST",
        f"{settings.device_service_url}/devices/{device_id}/confirm",
        api_key=_key_or_503(session.role, request),
    )
