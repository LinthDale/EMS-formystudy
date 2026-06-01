"""Device CRUD + lifecycle (OPS channel). Frozen-row mutations carry a freeze
override token so the DB trigger (migration 010/011) permits the legitimate edit."""
from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from ..auth import Channel, require
from ..models import DeviceCreate, DeviceOut, DeviceUpdate, OverrideRequest
from ..repositories import device_repo, signal_repo

router = APIRouter(prefix="/devices", tags=["devices"])
_OPS = require(Channel.OPS)


def _rid() -> str:
    return uuid.uuid4().hex


@router.post("", response_model=DeviceOut, status_code=201, dependencies=[_OPS])
async def create_device(body: DeviceCreate, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx() as conn:
        if await device_repo.get(conn, body.device_id):
            raise HTTPException(409, "device already exists")
        row = await device_repo.create(conn, body.model_dump())
    return dict(row)


@router.get("", response_model=list[DeviceOut], dependencies=[_OPS])
async def list_devices(request: Request, status: str | None = None, stale: bool | None = None) -> list[dict]:
    async with request.app.state.db.ops_pool.acquire() as conn:
        return [dict(r) for r in await device_repo.list_(conn, status, stale)]


@router.get("/{device_id}", response_model=DeviceOut, dependencies=[_OPS])
async def get_device(device_id: str, request: Request) -> dict:
    async with request.app.state.db.ops_pool.acquire() as conn:
        row = await device_repo.get(conn, device_id)
    if row is None:
        raise HTTPException(404, "device not found")
    return dict(row)


@router.patch("/{device_id}", response_model=DeviceOut, dependencies=[_OPS])
async def update_device(device_id: str, body: DeviceUpdate, request: Request) -> dict:
    db = request.app.state.db
    try:
        async with db.ops_tx() as conn:
            if await device_repo.get(conn, device_id) is None:
                raise HTTPException(404, "device not found")
            row = await device_repo.update(conn, device_id, body.model_dump(exclude_unset=True))
    except asyncpg.RaiseError as exc:
        raise HTTPException(409, f"frozen record — use /override ({exc})") from exc
    return dict(row)


@router.delete("/{device_id}", status_code=204, dependencies=[_OPS])
async def delete_device(device_id: str, request: Request) -> None:
    db = request.app.state.db
    async with db.ops_tx(freeze_override=_rid()) as conn:
        row = await device_repo.set_lifecycle(conn, device_id, status="retired")
    if row is None:
        raise HTTPException(404, "device not found")


@router.post("/{device_id}/confirm", response_model=DeviceOut, dependencies=[_OPS])
async def confirm_device(device_id: str, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx() as conn:  # candidate is not frozen -> no override needed
        row = await device_repo.set_lifecycle(
            conn, device_id, status="confirmed", classified_by="human", set_confirmed_at=True
        )
    if row is None:
        raise HTTPException(404, "device not found")
    return dict(row)


@router.post("/{device_id}/override", response_model=DeviceOut, dependencies=[_OPS])
async def override_device(device_id: str, body: OverrideRequest, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx(freeze_override=_rid()) as conn:
        if await device_repo.get(conn, device_id) is None:
            raise HTTPException(404, "device not found")
        row = await device_repo.set_lifecycle(
            conn, device_id, status="confirmed", classified_by="manual_override",
            device_type=body.device_type, set_confirmed_at=True,
        )
        for s in await signal_repo.list_active(conn, device_id):
            await signal_repo.retire(conn, device_id, s["signal_name"])
        for sig in body.signals:
            await signal_repo.add(conn, device_id, sig.model_dump())
    return dict(row)


@router.post("/{device_id}/reject", response_model=DeviceOut, dependencies=[_OPS])
async def reject_device(device_id: str, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx(freeze_override=_rid()) as conn:
        row = await device_repo.set_lifecycle(conn, device_id, status="retired")
    if row is None:
        raise HTTPException(404, "device not found")
    return dict(row)