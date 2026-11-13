"""Per-device measurement PRODUCT facade (ADR-025, refines PRD-0005 §8.2).

    GET /api/devices/{device_id}/measurements
        ?since=<ISO8601>&limit=<1..1000, default 100>&order=<asc|desc, default desc>

Why this exists: the legacy GET /api/measurements/{domain} forwarded raw PostgREST
operators (eq./gte./order column) straight from the browser. This facade exposes
PRODUCT semantics only — the browser never constructs a PostgREST query. The BFF:

  1. validates the product params (ISO8601 since, limit 1..max, order allowlist),
  2. resolves the device's domain from its device-service record (gateway_id ->
     electricity|factory view, bff.domain) — this read needs the OPS channel, so
     the route is OPS-gated,
  3. translates since/limit/order into PostgREST params SERVER-SIDE and reads the
     matching api.* view (web_anon, NO key spent on this hop — §9.3).
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import Response

from ..domain import resource_for_gateway
from ..roles import Role, channel_key_for
from ..security import require_roles
from ..sessions import Session
from ..upstream import forward

router = APIRouter(prefix="/api/devices", tags=["measurements"])

DEVICE_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"  # FR-322, spec-locked
_ORDER_TO_POSTGREST = {"asc": "time.asc", "desc": "time.desc"}
# product-facing query params (deny-by-default: anything else is a 422, matching
# the allowlist discipline of routes/devices.py and routes/measurements.py)
_FACADE_PARAMS = frozenset({"since", "limit", "order"})


def _reject_unknown_params(request: Request) -> None:
    for name in request.query_params:
        if name not in _FACADE_PARAMS:
            raise HTTPException(status_code=422, detail=f"unknown query parameter: {name}")


def _validated_since(since: str | None) -> str | None:
    """Validate an ISO8601 instant and return the PostgREST `time` filter value.

    Returns None when no `since` is given (no time filter forwarded). Raises 422
    on anything datetime.fromisoformat cannot parse (strict ISO8601; 'Z' allowed)."""
    if since is None:
        return None
    try:
        datetime.fromisoformat(since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="since must be an ISO8601 timestamp") from exc
    return f"gte.{since}"


@router.get("/{device_id}/measurements")
async def device_measurements(
    request: Request,
    device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    since: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    order: str = Query(default="desc"),
    session: Session = require_roles(Role.OPS),
) -> Response:
    """FR-520/521 per-device measurement facade. OPS-gated (the device-record
    lookup uses the OPS channel); the PostgREST read spends no key channel."""
    settings = request.app.state.settings
    _reject_unknown_params(request)
    if order not in _ORDER_TO_POSTGREST:
        raise HTTPException(status_code=422, detail="order must be asc or desc")
    effective_limit = settings.measurements_default_limit if limit is None else limit
    if not 1 <= effective_limit <= settings.measurements_max_limit:
        raise HTTPException(
            status_code=422, detail=f"limit must be 1..{settings.measurements_max_limit}"
        )
    time_filter = _validated_since(since)

    # 1) resolve device -> domain via the OPS channel (status/gateway are privileged)
    ops_key = channel_key_for(session.role, settings)
    if ops_key is None:  # fail closed — never borrow another role's channel
        raise HTTPException(status_code=503, detail="channel key not configured")
    record = await _device_record(request, device_id, ops_key)
    resource = resource_for_gateway(record.get("gateway_id"))
    if resource is None:
        raise HTTPException(status_code=404, detail="device has no measurement domain")

    # 2) read the matching PostgREST view, no key, browser-invisible operators
    params = {"device_id": f"eq.{device_id}", "order": _ORDER_TO_POSTGREST[order],
              "limit": str(effective_limit)}
    if time_filter is not None:
        params["time"] = time_filter
    return await forward(
        request.app.state.http, "GET", f"{settings.postgrest_url}{resource}", params=params
    )


async def _device_record(request: Request, device_id: str, api_key: str) -> dict:
    """Fetch the device-service record for domain resolution. Reuses forward() so
    upstream errors (502 on misconfig/5xx, contract 4xx pass-through) are mapped
    identically to every other proxied read. A 404 device propagates as the
    upstream's 404; a 200 with a non-object body is an upstream contract breach."""
    resp = await forward(
        request.app.state.http, "GET",
        f"{request.app.state.settings.device_service_url}/devices/{device_id}",
        api_key=api_key,
    )
    if resp.status_code != 200:
        # contract 4xx (e.g. 404 unknown device) passed through by forward(): relay it
        raise HTTPException(status_code=resp.status_code, detail="device not found")
    try:
        record = json.loads(bytes(resp.body))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="upstream error") from exc
    if not isinstance(record, dict):
        raise HTTPException(status_code=502, detail="upstream error")
    return record
