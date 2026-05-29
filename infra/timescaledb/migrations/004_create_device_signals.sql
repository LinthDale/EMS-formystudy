-- Migration: 004_create_device_signals
-- PRD-0003 §7.2 — 異質訊號定義（current-state + soft delete，見 ADR-011）。
-- Idempotent。
BEGIN;

CREATE TABLE IF NOT EXISTS public.device_signals (
    id              BIGSERIAL     PRIMARY KEY,
    device_id       TEXT          NOT NULL REFERENCES public.devices (device_id) ON DELETE CASCADE,
    signal_name     TEXT          NOT NULL,
    unit            TEXT,
    datatype        TEXT,
    direction       TEXT,
    source_ref      TEXT,
    status          TEXT          NOT NULL DEFAULT 'active',
    confirmed_by_ai BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    retired_at      TIMESTAMPTZ,
    metadata        JSONB         NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT device_signals_status_chk    CHECK (status IN ('active', 'retired')),
    CONSTRAINT device_signals_datatype_chk  CHECK (datatype IS NULL OR datatype IN ('float', 'int', 'bool', 'enum')),
    CONSTRAINT device_signals_direction_chk CHECK (direction IS NULL OR direction IN ('read', 'write', 'read_write'))
);

-- 同一裝置的同名訊號 active 版本唯一；已 retired 的不阻擋新增（ADR-011）。
CREATE UNIQUE INDEX IF NOT EXISTS device_signals_active_uniq
    ON public.device_signals (device_id, signal_name) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_device_signals_device_id ON public.device_signals (device_id);

COMMIT;
NOTIFY pgrst, 'reload schema';
