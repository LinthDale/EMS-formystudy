"""GET /healthz — liveness + both DB pools (FR-314)."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..models import HealthOut

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
async def healthz(request: Request, response: Response) -> HealthOut:
    pools = await request.app.state.db.healthz()
    ok = all(v == "ok" for v in pools.values())
    if not ok:
        response.status_code = 503
    return HealthOut(status="ok" if ok else "degraded", pools=pools)