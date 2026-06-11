"""Measurement proxy -> PostgREST :3001 (PRD-0005 §9.3, BFF-mediated).

The browser NEVER talks to PostgREST: zero CORS surface, PostgREST stays on the
internal network. Reads hit the anonymous `api.*` whitelist views, so NO key
channel is spent here — any authenticated session may read, but always through
an allowlisted, value-validated, limit-capped query.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ..roles import Role
from ..security import require_roles
from ..sessions import Session
from ..upstream import forward

router = APIRouter(prefix="/api/measurements", tags=["measurements"])

# domain -> PostgREST resource (api.* views from migrations 000/001, §1.5 D2)
_DOMAIN_RESOURCES: dict[str, str] = {
    "electricity": "/electricity_measurements",
    "factory": "/factory_measurements",
}
_ALLOWED_PARAMS = frozenset({"device_id", "time", "limit", "offset", "order"})
# PostgREST operator values: e.g. "eq.sim-001", "gte.2026-06-11T00:00:00Z", "time.desc"
_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:,+-]{1,128}$")


def _validated_params(request: Request, default_limit: int, max_limit: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in request.query_params.multi_items():
        if name not in _ALLOWED_PARAMS:
            raise HTTPException(status_code=422, detail=f"unknown query parameter: {name}")
        if name in out:
            raise HTTPException(status_code=422, detail=f"duplicate query parameter: {name}")
        if name == "limit":
            if not (value.isdigit() and 1 <= int(value) <= max_limit):
                raise HTTPException(status_code=422, detail=f"limit must be 1..{max_limit}")
        elif name == "offset":
            if not (value.isdigit() and int(value) <= 10_000_000):
                raise HTTPException(status_code=422, detail="offset must be a non-negative integer")
        elif not _VALUE_RE.fullmatch(value):
            raise HTTPException(status_code=422, detail=f"invalid value for {name}")
        out[name] = value
    out.setdefault("limit", str(default_limit))  # unbounded reads are never forwarded
    return out


@router.get("/{domain}")
async def read_measurements(
    domain: str,
    request: Request,
    session: Session = require_roles(Role.OPS, Role.INGEST, Role.READONLY),
) -> Response:
    """FR-520/521 data source (P1 exposes the secure route template; charts are P2)."""
    resource = _DOMAIN_RESOURCES.get(domain)
    if resource is None:
        raise HTTPException(status_code=404, detail="unknown measurement domain")
    settings = request.app.state.settings
    params = _validated_params(
        request, settings.measurements_default_limit, settings.measurements_max_limit
    )
    # web_anon read — deliberately NO api_key: this hop spends no key channel
    return await forward(
        request.app.state.http,
        "GET",
        f"{settings.postgrest_url}{resource}",
        params=params,
    )
