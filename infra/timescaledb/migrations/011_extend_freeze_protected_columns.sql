-- Migration: 011_extend_freeze_protected_columns
-- ADR-018 / Phase 1.1 弱點掃描 Finding B — 擴充 freeze 保護欄位集。
-- 010 只擋 device_type/status/classified_by/gateway_id；本支加入人工策展身分欄位
-- vendor/model/location/protocol。CREATE OR REPLACE 取代 010 的函式體（trigger 不動，
-- 仍指向同名函式）。metadata/ai_confidence/ai_provider/last_error 維持可寫
-- （FR-335 要求 AI 在凍結裝置寫 metadata.drift_detected_at + last_seen_at；
--  metadata 整欄覆寫防護見 ADR-018，落在 app 層）。
-- Idempotent：CREATE OR REPLACE FUNCTION。
BEGIN;

CREATE OR REPLACE FUNCTION public.enforce_freeze_rule() RETURNS trigger AS $fn$
DECLARE
    override_token TEXT;
BEGIN
    IF OLD.classified_by IN ('human', 'manual_override', 'migration_backfill')
       AND (NEW.device_type   IS DISTINCT FROM OLD.device_type
            OR NEW.status        IS DISTINCT FROM OLD.status
            OR NEW.classified_by IS DISTINCT FROM OLD.classified_by
            OR NEW.gateway_id    IS DISTINCT FROM OLD.gateway_id
            OR NEW.vendor        IS DISTINCT FROM OLD.vendor
            OR NEW.model         IS DISTINCT FROM OLD.model
            OR NEW.location      IS DISTINCT FROM OLD.location
            OR NEW.protocol      IS DISTINCT FROM OLD.protocol) THEN

        IF current_user = 'device_service_ai' THEN
            RAISE EXCEPTION 'frozen_record_ai: ai role cannot mutate frozen device (classified_by=%)', OLD.classified_by;
        END IF;

        override_token := current_setting('device_service.freeze_override', true);
        IF override_token IS NULL OR override_token = '' THEN
            RAISE EXCEPTION 'frozen_record_ops: ops role must SET LOCAL device_service.freeze_override=<request_id> before mutating frozen record (classified_by=%)', OLD.classified_by;
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

COMMIT;
NOTIFY pgrst, 'reload schema';