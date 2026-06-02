"""Human-correction write/list/deactivate orchestration (PRD-0003 §8.6 / FR-330/341/343).

Extracted from routes/devices.py so the router stays thin. HTTP-agnostic: raises
CorrectionRejected (text validation) and CorrectionServiceError(status, detail); the
API layer maps those to responses. Every mutating action persists a device_audit_log
row (atomic with the mutation), plus an interim structured log line.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from .correction_validator import validate_correction_text
from .key_id import hash_key_id
from .models import CorrectionCreate
from .repositories import audit_repo, correction_repo, device_repo

_audit = logging.getLogger("device_service.audit")

KEY_LIMIT_PER_HOUR = 30      # FR-343
DEVICE_LIMIT_PER_HOUR = 10   # FR-343
DEACTIVATE_ALERT_1H = 5      # FR-344 (WARN-6): per-key mass-deactivate sliding window
DEACTIVATE_ALERT_24H = 20


def mass_deactivate_suspicious(count_1h: int, count_24h: int) -> bool:
    """FR-344: one OPS key deactivating many corrections in a short window is a poisoning /
    tampering signal. Counts INCLUDE the current deactivate. The Telegram alert itself is a
    Grafana SQL alert over device_audit_log; here we mark the row + log the crossing."""
    return count_1h >= DEACTIVATE_ALERT_1H or count_24h >= DEACTIVATE_ALERT_24H


class CorrectionServiceError(Exception):
    """HTTP-agnostic domain error carrying the status the API layer should return."""

    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _rid() -> str:
    return uuid.uuid4().hex


class CorrectionService:
    def __init__(self, db, settings):
        self._db = db
        self._settings = settings

    def _key_identity(self, raw_key: str | None) -> tuple[str, str]:
        """Required identity for a correction WRITE (created_by_key_id is NOT NULL).
        503 if AUDIT_HASH_SALT is unset."""
        try:
            kid = hash_key_id(raw_key or "", self._settings.audit_hash_salt, self._settings.audit_salt_version)
        except ValueError as exc:
            raise CorrectionServiceError(503, f"audit identity unavailable: {exc}") from exc
        return kid, self._settings.audit_salt_version

    def _optional_identity(self, raw_key: str | None) -> tuple[str | None, str | None]:
        """Best-effort identity for AUDIT attribution where a missing salt must not fail
        the action (e.g. deactivate). Returns (None, None) if the salt is unset."""
        try:
            kid = hash_key_id(raw_key or "", self._settings.audit_hash_salt, self._settings.audit_salt_version)
            return kid, self._settings.audit_salt_version
        except ValueError:
            return None, None

    async def create_feedback(self, device_id: str, body: CorrectionCreate, raw_key: str | None) -> dict:
        human_explanation = validate_correction_text(body.human_explanation)  # CorrectionRejected -> 400
        key_id, salt_ver = self._key_identity(raw_key)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        data = body.model_dump(exclude={"rerun_classification", "demote_to_candidate"})
        data.update(device_id=device_id, human_explanation=human_explanation,
                    created_by_key_id=key_id, salt_version=salt_ver,
                    prompt_version_at_correction=_prompt_version())
        rid = _rid()
        override = rid if body.demote_to_candidate else None

        rejected_scope: str | None = None
        async with self._db.ops_tx(lock=device_id, freeze_override=override) as conn:
            # FR-343 per-key HARD limit: serialise same-key submissions across devices too.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('correction-key:'||$1, 0))", key_id)
            current = await device_repo.get(conn, device_id)
            if current is None:
                raise CorrectionServiceError(404, "device not found")
            if body.demote_to_candidate and current["status"] != "confirmed":
                raise CorrectionServiceError(
                    409, f"demote_to_candidate only applies to a confirmed device (status={current['status']!r})")
            over_key = await correction_repo.count_recent_by_key(conn, key_id, since) >= KEY_LIMIT_PER_HOUR
            over_device = (not over_key) and (
                await correction_repo.count_recent_by_device(conn, device_id, since) >= DEVICE_LIMIT_PER_HOUR)
            if over_key or over_device:
                rejected_scope = "key" if over_key else "device"
            else:
                rec = await correction_repo.create(conn, data)
                await audit_repo.record(
                    conn, event_type="ai_feedback_create", actor="ops", device_id=device_id,
                    actor_key_id=key_id, salt_version=salt_ver, correction_id=rec["id"],
                    outcome="success", detail={"verdict": body.verdict})
                if body.demote_to_candidate:
                    if await device_repo.demote_to_candidate(conn, device_id) is None:
                        raise CorrectionServiceError(404, "device not found")
                    await audit_repo.record(
                        conn, event_type="demote", actor="ops", device_id=device_id,
                        actor_key_id=key_id, salt_version=salt_ver, correction_id=rec["id"],
                        request_id=rid, outcome="success", detail={"from_status": current["status"]})
                    _audit.info("ai_feedback_demote device=%s from_status=%s correction_id=%s request_id=%s actor=ops",
                                device_id, current["status"], rec["id"], rid)
                return rec
        # rejected: record the rate-limit event in a SEPARATE committed tx — the main tx
        # above wrote nothing (and would roll back an in-tx audit row on the 429 raise).
        async with self._db.ops_tx() as conn:
            await audit_repo.record(
                conn, event_type="rate_limit_exceeded", actor="ops", device_id=device_id,
                actor_key_id=key_id, salt_version=salt_ver, outcome="rate_limited",
                detail={"scope": rejected_scope})
        _audit.warning("ai_feedback_rate_limited scope=%s key_id=%s device=%s", rejected_scope, key_id, device_id)
        limit = KEY_LIMIT_PER_HOUR if rejected_scope == "key" else DEVICE_LIMIT_PER_HOUR
        raise CorrectionServiceError(429, f"correction rate limit exceeded: per-{rejected_scope} {limit}/hour")

    async def list_feedback(self, device_id: str, *, active_only: bool) -> list[dict]:
        async with self._db.ops_pool.acquire() as conn:
            if await device_repo.get(conn, device_id) is None:
                raise CorrectionServiceError(404, "device not found")
            return await correction_repo.list_for_device(conn, device_id, active_only=active_only)

    async def deactivate(self, device_id: str, correction_id: int, reason_raw: str, raw_key: str | None) -> dict:
        reason = validate_correction_text(reason_raw)  # CorrectionRejected -> 400
        key_id, salt_ver = self._optional_identity(raw_key)  # best-effort (no 503 for a deactivate)
        detail: dict = {}
        suspicious = False
        async with self._db.ops_tx() as conn:
            if await device_repo.get(conn, device_id) is None:
                raise CorrectionServiceError(404, "device not found")
            rec = await correction_repo.deactivate(conn, device_id, correction_id, reason)
            if rec is None:
                raise CorrectionServiceError(409, "correction not active or not found")
            if key_id:  # FR-344 per-key window. Counted BEFORE this row is inserted (append-only:
                now = datetime.now(timezone.utc)  # the row can't be marked afterwards), so the
                # `+ 1` below accounts for the current deactivate which is not yet in the table.
                c1h = await audit_repo.count_recent(
                    conn, event_type="deactivate", since=now - timedelta(hours=1), actor_key_id=key_id) + 1
                c24h = await audit_repo.count_recent(
                    conn, event_type="deactivate", since=now - timedelta(hours=24), actor_key_id=key_id) + 1
                suspicious = mass_deactivate_suspicious(c1h, c24h)
                if suspicious:
                    detail = {"suspicious": True, "count_1h": c1h, "count_24h": c24h}
            await audit_repo.record(
                conn, event_type="deactivate", actor="ops", device_id=device_id,
                actor_key_id=key_id, salt_version=salt_ver, correction_id=correction_id,
                outcome="success", detail=detail)
        if suspicious:
            _audit.warning("mass_deactivate_alert key_id=%s device=%s count_1h=%s count_24h=%s (FR-344)",
                           key_id, device_id, detail["count_1h"], detail["count_24h"])
        else:
            _audit.info("correction_deactivated correction_id=%s device=%s actor=ops", correction_id, device_id)
        return rec


def _prompt_version() -> str:
    # imported lazily to avoid a module import cycle (prompt -> types -> ...)
    from .llm.prompt import PROMPT_VERSION
    return PROMPT_VERSION
