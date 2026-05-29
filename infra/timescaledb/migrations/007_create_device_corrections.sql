-- Migration: 007_create_device_corrections
-- PRD-0003 §7.3a — 人類修正回饋（永久保留，注入 LLM prompt 材料 + 審計，見 ADR-015）。
-- 內容級檢查（NFKC / injection regex）走應用層；此處加 DB 層長度 CHECK 作縱深防禦。
-- Idempotent。
BEGIN;

CREATE TABLE IF NOT EXISTS public.device_corrections (
    id                           BIGSERIAL   PRIMARY KEY,
    device_id                    TEXT        NOT NULL REFERENCES public.devices (device_id) ON DELETE CASCADE,
    verdict                      TEXT        NOT NULL,
    corrected_device_type        TEXT,
    corrected_signals            JSONB,
    human_explanation            TEXT        NOT NULL,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_key_id            TEXT        NOT NULL,
    salt_version                 TEXT        NOT NULL,
    prompt_version_at_correction TEXT,
    applied_count                INTEGER     NOT NULL DEFAULT 0,
    last_applied_at              TIMESTAMPTZ,
    is_active                    BOOLEAN     NOT NULL DEFAULT TRUE,
    deactivated_at               TIMESTAMPTZ,
    deactivation_reason          TEXT,
    CONSTRAINT corrections_verdict_chk
        CHECK (verdict IN ('wrong_classification', 'wrong_signals', 'wrong_unit', 'missed_signal', 'good_with_note')),
    CONSTRAINT corrections_explanation_len_chk
        CHECK (char_length(human_explanation) BETWEEN 30 AND 500),
    CONSTRAINT corrections_deactivation_reason_len_chk
        CHECK (deactivation_reason IS NULL OR char_length(deactivation_reason) BETWEEN 30 AND 500)
);

CREATE INDEX IF NOT EXISTS device_corrections_device_time
    ON public.device_corrections (device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS device_corrections_active_inject
    ON public.device_corrections (device_id, is_active, created_at DESC);

COMMIT;
NOTIFY pgrst, 'reload schema';
