"""Device CRUD + lifecycle (OPS channel). Frozen-row mutations carry a freeze
override token so the DB trigger (migration 010/011) permits the legitimate edit.

Override/reject emit a structured audit log line carrying the request id (interim
accountability until the dedicated audit table lands in Phase 1.4 observability)."""
from __future__ import annotations

import logging
import uuid

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request

from ..auth import Channel, require
from ..correction_service import CorrectionService, CorrectionServiceError
from ..discovery_pipeline import reclassify_device
from ..correction_validator import CorrectionRejected
from ..key_id import hash_key_id
from ..models import (
    CorrectionCreate,
    CorrectionDeactivateRequest,
    CorrectionOut,
    DeviceCreate,
    DeviceOut,
    DeviceUpdate,
    DigestOut,
    OverrideRequest,
)
from ..repositories import audit_repo, device_repo, digest_repo, signal_repo

router = APIRouter(prefix="/devices", tags=["devices"])
_OPS = require(Channel.OPS)
_audit = logging.getLogger("device_service.audit")
_log = logging.getLogger("device_service.routes.devices")


def _rid() -> str:
    return uuid.uuid4().hex


async def _call(coro):
    """Run a CorrectionService coroutine, mapping its HTTP-agnostic domain errors to HTTP
    responses (keeps the service free of FastAPI)."""
    try:
        return await coro
    except CorrectionRejected as exc:   # §7.3a content-rule violation -> 400
        raise HTTPException(400, {"reason": exc.reason, "message": str(exc)}) from exc
    except CorrectionServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


def _optional_key_id(raw_key: str | None, request: Request) -> tuple[str | None, str | None]:
    """Best-effort (key_id, salt_version) for AUDIT ATTRIBUTION on lifecycle actions
    (override/reject). Unlike a correction write, a lifecycle op must NOT fail just
    because AUDIT_HASH_SALT is unset (that salt is a corrections concern) — so a missing
    salt yields (None, None) and the audit row records actor='ops' without a key id."""
    settings = request.app.state.settings
    try:
        kid = hash_key_id(raw_key or "", settings.audit_hash_salt, settings.audit_salt_version)
        return kid, settings.audit_salt_version
    except ValueError:
        return None, None


@router.post("", response_model=DeviceOut, status_code=201, dependencies=[_OPS])
async def create_device(body: DeviceCreate, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx(lock=body.device_id) as conn:
        if await device_repo.get(conn, body.device_id):
            raise HTTPException(409, "device already exists")
        row = await device_repo.create(conn, body.model_dump())
    return dict(row)


@router.get("", response_model=list[DeviceOut], dependencies=[_OPS])
async def list_devices(request: Request, status: str | None = None, stale: bool | None = None) -> list[dict]:
    async with request.app.state.db.ops_pool.acquire() as conn:
        return [dict(r) for r in await device_repo.list_(conn, status, stale)]


@router.post("/{device_id}/ai-feedback", response_model=CorrectionOut, status_code=201, dependencies=[_OPS])
async def create_ai_feedback(
    device_id: str,
    body: CorrectionCreate,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """OPS human feedback (FR-330). Validation, audit identity, FR-343 rate limit, persist,
    optional demote + audit live in CorrectionService; the router maps domain errors to HTTP.
    rerun_classification (FR-330) triggers an on-demand reclassify AFTER the correction is
    committed, so the just-written correction is in the retrieval set (FR-331)."""
    db = request.app.state.db
    svc = CorrectionService(db, request.app.state.settings)
    rec = await _call(svc.create_feedback(device_id, body, x_api_key))
    if body.rerun_classification:
        # best-effort: re-run classification through the budget gate (FR-329) with a forced
        # cache miss. No-op if the device has no recent samples or is frozen (apply_outcome
        # skips a non-candidate). A failure must not undo the recorded correction — but log it
        # (don't swallow silently) so a real bug isn't indistinguishable from a legit no-op.
        try:
            outcome = await reclassify_device(db, request.app.state.classifier, request.app.state.settings,
                                              device_id=device_id, force=True)
            # transparency: tell the operator (via log) whether the rerun actually re-classified.
            # None = skipped (not a candidate / no samples / unknown gateway — see reclassify logs).
            if outcome is None:
                _log.info("rerun_classification device=%s: no-op (not re-classified; see reclassify log)", device_id)
            else:
                _log.info("rerun_classification device=%s: re-classified -> status=%s source=%s",
                          device_id, outcome.new_status, outcome.summary_source)
        except Exception:  # noqa: BLE001 — rerun is best-effort; correction is the primary write
            _log.warning("rerun_classification failed device=%s (correction kept)", device_id, exc_info=True)
    return rec


@router.get("/{device_id}/corrections", response_model=list[CorrectionOut], dependencies=[_OPS])
async def list_corrections(device_id: str, request: Request, active_only: bool = False) -> list[dict]:
    svc = CorrectionService(request.app.state.db, request.app.state.settings)
    return await _call(svc.list_feedback(device_id, active_only=active_only))


@router.post("/{device_id}/corrections/{correction_id}/deactivate", response_model=CorrectionOut, dependencies=[_OPS])
async def deactivate_correction(
    device_id: str,
    correction_id: int,
    body: CorrectionDeactivateRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    svc = CorrectionService(request.app.state.db, request.app.state.settings)
    return await _call(svc.deactivate(device_id, correction_id, body.reason, x_api_key))


@router.get("/{device_id}/human-review", response_model=DigestOut, dependencies=[_OPS])
async def human_review(device_id: str, request: Request) -> dict:
    """Return the stored human-review digest (§8.4). Read-only: never calls the LLM.
    A system_fallback digest is returned with 200 just like an llm one. 404 if the
    device is unknown or has no digest yet (e.g. a migration-backfilled device).
    Declared before GET /{device_id} (specific-before-general convention)."""
    async with request.app.state.db.ops_pool.acquire() as conn:
        exists, rec = await digest_repo.get_with_device(conn, device_id)
    if not exists:
        raise HTTPException(404, "device not found")
    if rec is None:
        raise HTTPException(404, "no review digest for device")
    return rec


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
        async with db.ops_tx(lock=device_id) as conn:
            if await device_repo.get(conn, device_id) is None:
                raise HTTPException(404, "device not found")
            row = await device_repo.update(conn, device_id, body.model_dump(exclude_unset=True))
    except asyncpg.RaiseError as exc:
        raise HTTPException(409, f"frozen record — use /override ({exc})") from exc
    return dict(row)


@router.delete("/{device_id}", status_code=204, dependencies=[_OPS])
async def delete_device(device_id: str, request: Request) -> None:
    # No freeze override here: a frozen device cannot be silently retired via DELETE;
    # the trigger blocks it -> 409 directing the caller to the explicit /reject path.
    db = request.app.state.db
    try:
        async with db.ops_tx(lock=device_id) as conn:
            row = await device_repo.set_lifecycle(conn, device_id, status="retired")
    except asyncpg.RaiseError as exc:
        raise HTTPException(409, f"frozen device — use POST /devices/{device_id}/reject ({exc})") from exc
    if row is None:
        raise HTTPException(404, "device not found")


@router.post("/{device_id}/confirm", response_model=DeviceOut, dependencies=[_OPS])
async def confirm_device(device_id: str, request: Request) -> dict:
    db = request.app.state.db
    async with db.ops_tx(lock=device_id) as conn:  # candidate is not frozen -> no override needed
        current = await device_repo.get(conn, device_id)
        if current is None:
            raise HTTPException(404, "device not found")
        if current["status"] != "candidate":
            raise HTTPException(409, f"device is in '{current['status']}' state, not 'candidate'")
        row = await device_repo.set_lifecycle(
            conn, device_id, status="confirmed", classified_by="human", set_confirmed_at=True
        )
    return dict(row)


@router.post("/{device_id}/override", response_model=DeviceOut, dependencies=[_OPS])
async def override_device(
    device_id: str, body: OverrideRequest, request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    db = request.app.state.db
    rid = _rid()
    key_id, salt_ver = _optional_key_id(x_api_key, request)
    async with db.ops_tx(freeze_override=rid, lock=device_id) as conn:
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
        await audit_repo.record(  # atomic with the freeze-override mutation (§554 / §8.7.5)
            conn, event_type="freeze_override", actor="ops", device_id=device_id,
            actor_key_id=key_id, salt_version=salt_ver, request_id=rid, outcome="success",
            detail={"action": "override", "new_device_type": body.device_type})
    _audit.info("freeze_override action=override device=%s request_id=%s actor=ops", device_id, rid)
    return dict(row)


@router.post("/{device_id}/reject", response_model=DeviceOut, dependencies=[_OPS])
async def reject_device(
    device_id: str, request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    db = request.app.state.db
    rid = _rid()
    key_id, salt_ver = _optional_key_id(x_api_key, request)
    async with db.ops_tx(freeze_override=rid, lock=device_id) as conn:
        row = await device_repo.set_lifecycle(conn, device_id, status="retired")
        if row is None:
            raise HTTPException(404, "device not found")  # rolls back (nothing was updated)
        await audit_repo.record(
            conn, event_type="freeze_override", actor="ops", device_id=device_id,
            actor_key_id=key_id, salt_version=salt_ver, request_id=rid, outcome="success",
            detail={"action": "reject"})
    _audit.info("freeze_override action=reject device=%s request_id=%s actor=ops", device_id, rid)
    return dict(row)
