"""Signal CRUD for a device (OPS channel)."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from ..auth import Channel, require
from ..models import SignalCreate, SignalOut
from ..repositories import device_repo, signal_repo

router = APIRouter(prefix="/devices/{device_id}/signals", tags=["signals"])
_OPS = require(Channel.OPS)


@router.get("", response_model=list[SignalOut], dependencies=[_OPS])
async def list_signals(device_id: str, request: Request) -> list[dict]:
    async with request.app.state.db.ops_pool.acquire() as conn:
        return [dict(r) for r in await signal_repo.list_active(conn, device_id)]


@router.post("", response_model=SignalOut, status_code=201, dependencies=[_OPS])
async def add_signal(device_id: str, body: SignalCreate, request: Request) -> dict:
    db = request.app.state.db
    try:
        async with db.ops_tx() as conn:
            if await device_repo.get(conn, device_id) is None:
                raise HTTPException(404, "device not found")
            row = await signal_repo.add(conn, device_id, body.model_dump())
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "signal already active") from exc
    except asyncpg.RaiseError as exc:
        raise HTTPException(409, f"frozen record — use /override ({exc})") from exc
    return dict(row)


@router.delete("/{signal_name}", status_code=204, dependencies=[_OPS])
async def delete_signal(device_id: str, signal_name: str, request: Request) -> None:
    db = request.app.state.db
    try:
        async with db.ops_tx() as conn:
            removed = await signal_repo.retire(conn, device_id, signal_name)
    except asyncpg.RaiseError as exc:
        raise HTTPException(409, f"frozen record — use /override ({exc})") from exc
    if removed is None:
        raise HTTPException(404, "active signal not found")