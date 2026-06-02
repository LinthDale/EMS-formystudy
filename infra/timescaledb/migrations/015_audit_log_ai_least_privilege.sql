-- Migration: 015_audit_log_ai_least_privilege
-- PRD-0003 §8.6.1 least-privilege (review #4). Migration 014 granted device_service_ai
-- SELECT + INSERT on device_audit_log. The AI role only ever WRITES audit rows
-- (guardrail_block, FR-339); it has no need to READ the audit trail, which contains OPS
-- actions (override/reject/demote/deactivate) and actor_key_id attribution. Revoke the
-- AI read so a compromised AI connection cannot enumerate operator audit detail. OPS keeps
-- SELECT (operator console + the FR-344 window count run as OPS). FR-339/FR-344 alerts are
-- Grafana SQL window queries (run with their own DB user), not the AI role.
-- A full REVOKE SELECT would also break `INSERT ... RETURNING id` (RETURNING needs SELECT on
-- the returned column), so this is COLUMN-SCOPED: AI keeps SELECT on the surrogate `id` only
-- (enough for RETURNING id and a bare count(*)), but loses read access to every content column
-- (detail / actor_key_id / request_id / correction_id / outcome / …). So AI can write its
-- guardrail_block rows and reference their id, but cannot enumerate operator audit detail.
-- OPS is unchanged (full SELECT). Idempotent.
BEGIN;

REVOKE SELECT ON public.device_audit_log FROM device_service_ai;
GRANT SELECT (id) ON public.device_audit_log TO device_service_ai;

COMMIT;
