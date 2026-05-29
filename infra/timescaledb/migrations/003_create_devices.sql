-- Migration: 003_create_devices
-- PRD-0003 §7.1 — device registry 主表（一般表，非 hypertable）。
-- Idempotent — CREATE TABLE/INDEX IF NOT EXISTS；重複執行安全。
BEGIN;

CREATE TABLE IF NOT EXISTS public.devices (
    device_id       TEXT          PRIMARY KEY,
    device_type     TEXT,
    status          TEXT          NOT NULL DEFAULT 'candidate',
    protocol        TEXT,
    vendor          TEXT,
    model           TEXT,
    location        TEXT,
    gateway_id      TEXT,
    classified_by   TEXT,
    ai_confidence   NUMERIC(3,2),
    ai_provider     TEXT,
    last_error      TEXT,
    metadata        JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ,
    confirmed_at    TIMESTAMPTZ,
    activated_at    TIMESTAMPTZ,
    stale_marked_at TIMESTAMPTZ,
    CONSTRAINT devices_status_chk
        CHECK (status IN ('candidate', 'confirmed', 'active', 'maintenance', 'retired')),
    CONSTRAINT devices_classified_by_chk
        CHECK (classified_by IS NULL OR classified_by IN ('human', 'ai', 'manual_override', 'migration_backfill')),
    CONSTRAINT devices_ai_confidence_chk
        CHECK (ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_devices_status          ON public.devices (status);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen_at    ON public.devices (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_devices_device_type     ON public.devices (device_type);
CREATE INDEX IF NOT EXISTS idx_devices_stale_marked_at ON public.devices (stale_marked_at);

COMMIT;
NOTIFY pgrst, 'reload schema';
