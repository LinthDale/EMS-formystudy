"""Device proxy routes -> device-service REST :8002 (the secure template).

PRD-0005 §8.1 surface (all OPS-gated, X-API-Key injected server-side, device_id
path-validated against the FR-322 regex BEFORE anything goes upstream, errors
mapped per upstream.py):
- GET  /api/devices                      FR-500 privileged list
- GET  /api/devices/{id}                 FR-501 detail
- GET  /api/devices/{id}/signals         FR-501 signals
- GET  /api/devices/{id}/human-review    FR-511 review digest
- POST /api/devices/{id}/confirm         FR-512 confirm
- POST /api/devices/{id}/override        FR-512 override (device_type + signals)
- POST /api/devices/{id}/reject          FR-512 reject
- POST /api/devices/{id}/corrections     FR-513 -> device-service POST /ai-feedback

Boundary rules: query params are deny-by-default allowlisted and re-validated
here (mirroring the device-service contract, openapi 1.3.0). Mutating routes are
additionally covered by the Origin-CSRF middleware. The per-device measurement
facade (GET /api/devices/{id}/measurements, ADR-025) lives in its own module.
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


async def _json_body(request: Request) -> dict:
    """Parse a mutating request body as a JSON object. The BFF does NOT re-impose
    the device-service schema (single source of truth, §9.6) — it only enforces
    that the payload is a JSON object so a malformed body fails fast at the
    boundary (422) instead of being forwarded as junk."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001 — any decode failure is a client 422
        raise HTTPException(status_code=422, detail="request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="request body must be a JSON object")
    return body


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


@router.get("/{device_id}")
async def get_device(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-501 device detail (status/classified_by/ai_confidence need the OPS channel)."""
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "GET",
        f"{settings.device_service_url}/devices/{device_id}",
        api_key=_key_or_503(session.role, request),
    )


@router.get("/{device_id}/signals")
async def get_device_signals(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-501 signals (signal status/source_ref are privileged -> OPS channel)."""
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "GET",
        f"{settings.device_service_url}/devices/{device_id}/signals",
        api_key=_key_or_503(session.role, request),
    )


@router.get("/{device_id}/human-review")
async def get_human_review(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-511 review digest (rendered as plain text by the SPA, §9.5)."""
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "GET",
        f"{settings.device_service_url}/devices/{device_id}/human-review",
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


@router.post("/{device_id}/override")
async def override_device(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-512 override: forward the client body (device_type + signals) to the
    device-service /override endpoint. device-service re-validates the body and
    owns the freeze-override + audit; the BFF never trusts client validation."""
    settings = request.app.state.settings
    body = await _json_body(request)
    return await forward(
        request.app.state.http,
        "POST",
        f"{settings.device_service_url}/devices/{device_id}/override",
        api_key=_key_or_503(session.role, request),
        json_body=body,
    )


@router.post("/{device_id}/reject")
async def reject_device(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-512 reject (retire a candidate); no body — device-service stamps the audit."""
    settings = request.app.state.settings
    return await forward(
        request.app.state.http,
        "POST",
        f"{settings.device_service_url}/devices/{device_id}/reject",
        api_key=_key_or_503(session.role, request),
    )


@router.post("/{device_id}/corrections")
async def create_correction(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-513 correction. device-service exposes this as POST /ai-feedback (the
    /corrections collection there is read-only GET); the product-facing route is
    /corrections, the verified upstream path is /ai-feedback. Body validated by
    device-service (§7.3a); the BFF forwards it verbatim with the OPS key."""
    settings = request.app.state.settings
    body = await _json_body(request)
    return await forward(
        request.app.state.http,
        "POST",
        f"{settings.device_service_url}/devices/{device_id}/ai-feedback",
        api_key=_key_or_503(session.role, request),
        json_body=body,
    )
