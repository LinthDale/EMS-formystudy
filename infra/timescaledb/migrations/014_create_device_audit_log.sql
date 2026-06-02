-- Migration: 014_create_device_audit_log
-- PRD-0003 §8.7.5 / FR-339 / FR-344 / §7.5 — persistent audit trail (replaces the
-- interim structured-log-only accountability noted in routes/devices.py).
--
-- Generic append-only event table covering every audited action:
--   freeze_override (override/reject/delete token use), ai_feedback_create, demote,
--   deactivate, rate_limit_exceeded, guardrail_block (L2 pre/post), status_advance.
-- Event-specific fields live in `detail` JSONB (e.g. from_status, scope, phase,
-- threat_category, l1_input_hash, l1_output_hash, reason) so the schema is stable.
--
-- APPEND-ONLY: neither role gets UPDATE/DELETE (tamper resistance). No FK on device_id
-- so an audit row SURVIVES device deletion. Both AI (guardrail_block path) and OPS
-- (lifecycle/correction actions) may INSERT + SELECT (FR-339/FR-344 window counts).
-- Idempotent.
BEGIN;

CREATE TABLE IF NOT EXISTS public.device_audit_log (
    id            BIGSERIAL    PRIMARY KEY,
    event_time    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    event_type    TEXT         NOT NULL,
    device_id     TEXT,                       -- no FK: audit must outlive the device
    actor         TEXT         NOT NULL,      -- 'ops' | 'ai' | 'system'
    actor_key_id  TEXT,                       -- HMAC key id (FR-345); never the raw key
    salt_version  TEXT,                       -- FR-345 lineage
    request_id    TEXT,                       -- freeze override token / correlation id
    correction_id BIGINT,
    outcome       TEXT,                       -- 'success'|'blocked'|'rejected'|'rate_limited'|...
    detail        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT device_audit_event_type_chk CHECK (event_type IN (
        'freeze_override', 'ai_feedback_create', 'demote', 'deactivate',
        'rate_limit_exceeded', 'guardrail_block', 'status_advance')),
    CONSTRAINT device_audit_actor_chk CHECK (actor IN ('ops', 'ai', 'system'))
);

-- FR-339: consecutive guardrail BLOCK per device / 1h.
CREATE INDEX IF NOT EXISTS device_audit_device_event_time
    ON public.device_audit_log (device_id, event_type, event_time DESC);
-- FR-344: deactivate count per key / sliding window.
CREATE INDEX IF NOT EXISTS device_audit_key_event_time
    ON public.device_audit_log (actor_key_id, event_type, event_time DESC);

-- append-only grants: INSERT + SELECT only (no UPDATE/DELETE for any service role)
GRANT INSERT, SELECT ON public.device_audit_log TO device_service_ai, device_service_ops;
GRANT USAGE, SELECT ON SEQUENCE public.device_audit_log_id_seq TO device_service_ai, device_service_ops;

COMMIT;
NOTIFY pgrst, 'reload schema';
