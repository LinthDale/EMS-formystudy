"""Bounded history/records product facade. PRD-0018 / ADR-027."""
from datetime import datetime, timezone
from math import ceil
from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import Response
from ..domain import resource_for_gateway
from ..roles import Role, channel_key_for
from ..security import require_roles
from ..sessions import Session
from ..upstream import forward
from .device_measurements import DEVICE_ID_PATTERN, _device_record

router = APIRouter(prefix="/api/devices", tags=["measurements"])
MAX_SPAN_SECONDS = 7 * 86400

def _range(request: Request, since: str, until: str, allowed: set[str]):
    names = [name for name, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)) or set(names) - allowed:
        raise HTTPException(422, "unknown or repeated query parameter")
    try:
        start, end = datetime.fromisoformat(since), datetime.fromisoformat(until)
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError()
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        span = (end - start).total_seconds()
        if not 0 < span <= MAX_SPAN_SECONDS:
            raise ValueError()
    except (ValueError, OverflowError):
        raise HTTPException(422, "since/until must have timezones and span >0 to 7 days")
    return start.isoformat(), end.isoformat(), span

async def _domain(request: Request, device_id: str, session: Session) -> str:
    key = channel_key_for(session.role, request.app.state.settings)
    if key is None:
        raise HTTPException(503, "channel key not configured")
    record = await _device_record(request, device_id, key)
    resource = resource_for_gateway(record.get("gateway_id"))
    if resource is None:
        raise HTTPException(404, "device has no measurement domain")
    return "electricity" if resource == "/electricity_measurements" else "factory"

@router.get("/{device_id}/history")
async def history(
    request: Request, device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    since: str = Query(), until: str = Query(),
    points: int = Query(default=600, ge=60, le=1200),
    session: Session = require_roles(Role.OPS),
) -> Response:
    start, end, span = _range(request, since, until, {"since", "until", "points"})
    domain = await _domain(request, device_id, session)
    return await forward(request.app.state.http, "GET",
        request.app.state.settings.postgrest_url + "/rpc/measurement_history",
        params={"p_device_id": device_id, "p_domain": domain,
                "p_since": start, "p_until": end,
                "p_step_seconds": str(max(1, ceil(span / points)))})

@router.get("/{device_id}/records")
async def records(
    request: Request, device_id: str = Path(pattern=DEVICE_ID_PATTERN),
    since: str = Query(), until: str = Query(),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=1000000),
    session: Session = require_roles(Role.OPS),
) -> Response:
    start, end, _ = _range(request, since, until, {"since", "until", "limit", "offset"})
    domain = await _domain(request, device_id, session)
    return await forward(request.app.state.http, "GET",
        request.app.state.settings.postgrest_url + "/rpc/measurement_records",
        params={"p_device_id": device_id, "p_domain": domain,
                "p_since": start, "p_until": end, "p_limit": str(limit), "p_offset": str(offset)})
