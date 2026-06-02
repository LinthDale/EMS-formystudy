"""Integration: audit_repo record + window-count (PRD-0003 §8.7.5 / FR-339 / FR-344).
device_audit_log is append-only (no DELETE grant), so counts use a since=cutoff captured
in-test to stay robust to rows accumulated by previous runs."""
import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.integration


async def _db():
    from device_service.config import Settings
    from device_service.db import Database
    settings = Settings(
        _env_file=None, db_host=os.getenv("EMS_DB_HOST", "timescaledb"), db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"))
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable: {exc}")
    return db


@pytest.fixture
async def db():
    d = await _db()
    yield d
    await d.close()


async def test_record_returns_id_and_count_recent_scopes(db):
    from device_service.repositories import audit_repo
    t0 = datetime.now(timezone.utc) - timedelta(seconds=1)
    async with db.ops_pool.acquire() as conn:
        # 3 guardrail blocks for one device, 2 deactivates for one key
        for _ in range(3):
            rid = await audit_repo.record(
                conn, event_type="guardrail_block", actor="ai", device_id="itest-audit-dev",
                outcome="blocked", detail={"phase": "pre", "threat_category": "prompt_injection"})
            assert isinstance(rid, int) and rid > 0
        for _ in range(2):
            await audit_repo.record(
                conn, event_type="deactivate", actor="ops", actor_key_id="itest-audit-kid",
                correction_id=7, outcome="success")

        # FR-339: per-device guardrail blocks since cutoff
        assert await audit_repo.count_recent(
            conn, event_type="guardrail_block", since=t0, device_id="itest-audit-dev") == 3
        # FR-344: per-key deactivates since cutoff
        assert await audit_repo.count_recent(
            conn, event_type="deactivate", since=t0, actor_key_id="itest-audit-kid") == 2
        # a future cutoff sees nothing
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert await audit_repo.count_recent(
            conn, event_type="guardrail_block", since=future, device_id="itest-audit-dev") == 0


async def test_record_rejects_unknown_event_type(db):
    from device_service.repositories import audit_repo
    with pytest.raises(ValueError):
        await audit_repo.record(None, event_type="not_a_real_event", actor="ops")  # raises before any DB use
