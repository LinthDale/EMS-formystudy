"""Device CRUD + lifecycle (OPS channel). Frozen-row mutations carry a freeze
override token so the DB trigger (migration 010/011) permits the legitimate edit.

Override/reject emit a structured audit log line carrying the request id (interim
accountability until the dedicated audit table lands in Phase 1.4 observability)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import uuid

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request

from ..auth import Channel, require
from ..correction_validator import CorrectionRejected, validate_correction_text
from ..key_id import hash_key_id
from ..llm.prompt import PROMPT_VERSION
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
from ..repositories import correction_repo, device_repo, digest_repo, signal_repo

router = APIRouter(prefix="/devices", tags=["devices"])
_OPS = require(Channel.OPS)
_audit = logging.getLogger("device_service.audit")
_CORRECTION_KEY_LIMIT_PER_HOUR = 30
_CORRECTION_DEVICE_LIMIT_PER_HOUR = 10


def _rid() -> str:
    return uuid.uuid4().hex


def _validated_correction_text(raw: str) -> str:
    try:
        return validate_correction_text(raw)
    except CorrectionRejected as exc:
        # FR-330 / FR-341: content-rule violation -> 400 (spec); pydantic body-shape
        # errors stay 422. detail carries the stable machine reason for clients.
        raise HTTPException(status_code=400, detail={"reason": exc.reason, "message": str(exc)}) from exc


def _created_by_key_id(raw_key: str | None, request: Request) -> str:
    settings = request.app.state.settings
    try:
        return hash_key_id(raw_key or "", settings.audit_hash_salt, settings.audit_salt_version)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"audit identity unavailable: {exc}") from exc


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
    """Persist OPS human feedback for later correction-loop retrieval.

    Free text is validated before persistence because it will later be injected
    into the classifier prompt. Raw API keys are never stored; audit identity is
    HMAC-derived from the presented OPS key and the configured audit salt.

    Rate-limit (FR-343) is a HARD limit on both axes: the per-device limit is
    serialised by the ops_tx(lock=device_id) advisory lock, and the per-key limit by
    a second 'correction-key:' advisory lock taken below (so the same key on different
    devices cannot concurrently overshoot). Both locks are transaction-scoped.
    """
    # FR-330 rerun_classification needs the on-demand reclassify pipeline (fetch recent raw
    # samples from the measurements tables via the OPS pool, §234/§761) — the same primitive
    # as the MCP classify_with_context tool, so it lands with that capability. Reject a true
    # value now rather than silently ignoring it. demote_to_candidate IS supported below.
    if body.rerun_classification:
        raise HTTPException(
            501, "rerun_classification not yet supported (needs the on-demand reclassify "
                 "pipeline shared with MCP classify_with_context)")

    human_explanation = _validated_correction_text(body.human_explanation)
    # _OPS dependency already guaranteed a non-empty valid OPS key; x_api_key is never None here.
    key_id = _created_by_key_id(x_api_key, request)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    data = body.model_dump(exclude={"rerun_classification", "demote_to_candidate"})
    data.update(
        device_id=device_id,
        human_explanation=human_explanation,
        created_by_key_id=key_id,
        salt_version=request.app.state.settings.audit_salt_version,
        prompt_version_at_correction=PROMPT_VERSION,  # server-stamped provenance, not client-supplied
    )

    # demote_to_candidate re-opens a (possibly frozen) device for review — needs the freeze
    # override token (§590 "ai-feedback (with demote)") so the trigger permits the status flip.
    rid = _rid()
    override = rid if body.demote_to_candidate else None
    db = request.app.state.db
    async with db.ops_tx(lock=device_id, freeze_override=override) as conn:
        # FR-343 per-key HARD limit: also serialise same-key submissions across devices
        # (the device lock only serialises per-device, so a single key hitting many devices
        # concurrently could otherwise overshoot). Acquired AFTER the device lock — no path
        # takes device-after-key, so the fixed order cannot deadlock.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('correction-key:'||$1, 0))", key_id)
        current = await device_repo.get(conn, device_id)
        if current is None:
            raise HTTPException(404, "device not found")
        # demote is ONLY the §885 confirmed->candidate transition. A candidate is already the
        # target (demoting would needlessly wipe classified_by); a retired device must not be
        # resurrected into the AI pipeline. Reject any non-confirmed demote before writing.
        if body.demote_to_candidate and current["status"] != "confirmed":
            raise HTTPException(
                409, f"demote_to_candidate only applies to a confirmed device (status={current['status']!r})")
        if await correction_repo.count_recent_by_key(conn, key_id, since) >= _CORRECTION_KEY_LIMIT_PER_HOUR:
            _audit.warning("ai_feedback_rate_limited scope=key key_id=%s device=%s", key_id, device_id)
            raise HTTPException(429, "correction rate limit exceeded: per-key 30/hour")
        if await correction_repo.count_recent_by_device(conn, device_id, since) >= _CORRECTION_DEVICE_LIMIT_PER_HOUR:
            _audit.warning("ai_feedback_rate_limited scope=device key_id=%s device=%s", key_id, device_id)
            raise HTTPException(429, "correction rate limit exceeded: per-device 10/hour")
        rec = await correction_repo.create(conn, data)
        if body.demote_to_candidate:
            if await device_repo.demote_to_candidate(conn, device_id) is None:
                raise HTTPException(404, "device not found")   # concurrent delete within the lock
            _audit.info("ai_feedback_demote device=%s from_status=%s correction_id=%s request_id=%s actor=ops",
                        device_id, current["status"], rec["id"], rid)
    return rec


@router.get("/{device_id}/corrections", response_model=list[CorrectionOut], dependencies=[_OPS])
async def list_corrections(device_id: str, request: Request, active_only: bool = False) -> list[dict]:
    async with request.app.state.db.ops_pool.acquire() as conn:
        if await device_repo.get(conn, device_id) is None:
            raise HTTPException(404, "device not found")
        return await correction_repo.list_for_device(conn, device_id, active_only=active_only)


@router.post("/{device_id}/corrections/{correction_id}/deactivate", response_model=CorrectionOut, dependencies=[_OPS])
async def deactivate_correction(
    device_id: str,
    correction_id: int,
    body: CorrectionDeactivateRequest,
    request: Request,
) -> dict:
    reason = _validated_correction_text(body.reason)
    async with request.app.state.db.ops_pool.acquire() as conn:
        if await device_repo.get(conn, device_id) is None:
            raise HTTPException(404, "device not found")
        rec = await correction_repo.deactivate(conn, device_id, correction_id, reason)
    if rec is None:
        raise HTTPException(409, "correction not active or not found")
    _audit.info("correction_deactivated correction_id=%s actor=ops", correction_id)
    return rec


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
async def override_device(device_id: str, body: OverrideRequest, request: Request) -> dict:
    db = request.app.state.db
    rid = _rid()
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
    _audit.info("freeze_override action=override device=%s request_id=%s actor=ops", device_id, rid)
    return dict(row)


@router.post("/{device_id}/reject", response_model=DeviceOut, dependencies=[_OPS])
async def reject_device(device_id: str, request: Request) -> dict:
    db = request.app.state.db
    rid = _rid()
    async with db.ops_tx(freeze_override=rid, lock=device_id) as conn:
        row = await device_repo.set_lifecycle(conn, device_id, status="retired")
    if row is None:
        raise HTTPException(404, "device not found")
    _audit.info("freeze_override action=reject device=%s request_id=%s actor=ops", device_id, rid)
    return dict(row)
