-- Migration: 012_grant_ai_correction_read
-- PRD-0003 §8.6.4 / §8.6.5 / §7.3a (FR-331 / FR-332).
--
-- The classification path runs as device_service_ai and must:
--   (a) READ relevant human corrections to inject them (sanitized, app-layer) into
--       the L1 prompt — FR-331 / §8.6.4 retrieval;
--   (b) bump injection bookkeeping (applied_count / last_applied_at) for the
--       corrections it actually injected — §7.3a applied_count.
--
-- It must NOT create or alter the HUMAN CONTENT of a correction. So this grant is
-- SELECT + a COLUMN-SCOPED UPDATE on (applied_count, last_applied_at) ONLY. The
-- migration-010 invariant "AI 不可寫 device_corrections 內容" stays true: no INSERT,
-- no DELETE, and no UPDATE on verdict / corrected_* / human_explanation / is_active /
-- created_by_key_id / salt_version / deactivation_*. PostgreSQL column privileges
-- enforce this at the DB layer (a column without UPDATE privilege cannot be set).
-- device_corrections has no freeze trigger, so the GRANT is the sole gate here.
--
-- Idempotent (GRANT is idempotent).
BEGIN;

GRANT SELECT ON public.device_corrections TO device_service_ai;
GRANT UPDATE (applied_count, last_applied_at) ON public.device_corrections TO device_service_ai;

COMMIT;
