-- Migration: 005_create_device_review_digests
-- PRD-0003 §7.3 — Human-review 摘要持久化（覆寫式，每 device 一份）。
-- Idempotent。
BEGIN;

CREATE TABLE IF NOT EXISTS public.device_review_digests (
    device_id      TEXT          PRIMARY KEY REFERENCES public.devices (device_id) ON DELETE CASCADE,
    digest         JSONB         NOT NULL,
    summary_source TEXT          NOT NULL,
    generated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    provider       TEXT,
    model          TEXT,
    prompt_version TEXT,
    CONSTRAINT review_digests_source_chk CHECK (summary_source IN ('llm', 'system_fallback'))
);

COMMIT;
NOTIFY pgrst, 'reload schema';
