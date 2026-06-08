-- Migration: 013_index_corrections_key_time
-- PRD-0003 FR-343 — per-key correction rate limit (count_recent_by_key) queries
-- device_corrections by (created_by_key_id, created_at). Migration 007 indexed only
-- (device_id, ...), so the per-key count would seq-scan as the table grows. Add the
-- supporting index. This is a hot path on every POST /ai-feedback.
-- Idempotent (CREATE INDEX IF NOT EXISTS).
BEGIN;

CREATE INDEX IF NOT EXISTS device_corrections_key_time
    ON public.device_corrections (created_by_key_id, created_at DESC);

COMMIT;
