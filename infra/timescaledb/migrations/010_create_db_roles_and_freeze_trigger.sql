-- Migration: 010_create_db_roles_and_freeze_trigger
-- PRD-0003 §7.5 / §8.6.2（S1 修法 v6）— DB role 拆分 + 凍結 trigger。
-- 即使 device-service 容器 RCE，凍結紀錄（classified_by IN human/manual_override/
-- migration_backfill）的主欄位 mutation 仍被 DB 擋下（見 ADR-015/016/017）。
-- Idempotent：role 用 pg_roles 檢查；function CREATE OR REPLACE；trigger DROP IF EXISTS 再建。
BEGIN;

-- 1. DB roles（per-role login，雙連線池用，見 ADR-017）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'device_service_ai') THEN
        CREATE ROLE device_service_ai NOINHERIT LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'device_service_ops') THEN
        CREATE ROLE device_service_ops NOINHERIT LOGIN;
    END IF;
END $$;

-- 2. 權限：AI 最小（不可寫 device_corrections、不可讀 measurements raw）
GRANT USAGE ON SCHEMA public TO device_service_ai, device_service_ops;
GRANT SELECT, INSERT, UPDATE ON
      public.devices, public.device_signals,
      public.device_review_digests, public.llm_budget_ledger
   TO device_service_ai;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO device_service_ai;

-- OPS 全權 + measurements raw SELECT（為 LLM 取樣本走 OPS pool）
GRANT ALL ON
      public.devices, public.device_signals, public.device_review_digests,
      public.device_corrections, public.llm_budget_ledger
   TO device_service_ops;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO device_service_ops;
GRANT SELECT ON public.electricity_measurements, public.factory_measurements
   TO device_service_ops;

-- 3. freeze override token（GUC）；trigger 讀 current_setting 判斷放行
ALTER DATABASE ems SET device_service.freeze_override TO '';

-- 4. 凍結 trigger：BOTH role 預設擋；AI 一律拒、OPS 須夾顯式 override token
CREATE OR REPLACE FUNCTION public.enforce_freeze_rule() RETURNS trigger AS $fn$
DECLARE
    override_token TEXT;
BEGIN
    IF OLD.classified_by IN ('human', 'manual_override', 'migration_backfill')
       AND (NEW.device_type   IS DISTINCT FROM OLD.device_type
            OR NEW.status        IS DISTINCT FROM OLD.status
            OR NEW.classified_by IS DISTINCT FROM OLD.classified_by
            OR NEW.gateway_id    IS DISTINCT FROM OLD.gateway_id) THEN

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

DROP TRIGGER IF EXISTS devices_freeze_check ON public.devices;
CREATE TRIGGER devices_freeze_check
    BEFORE UPDATE ON public.devices
    FOR EACH ROW EXECUTE FUNCTION public.enforce_freeze_rule();

-- 5. device_signals 同樣的雙重保護（父 device 凍結則 signals 亦凍）
CREATE OR REPLACE FUNCTION public.enforce_signals_freeze() RETURNS trigger AS $fn$
DECLARE
    parent_classified TEXT;
    override_token    TEXT;
BEGIN
    SELECT classified_by INTO parent_classified
    FROM public.devices WHERE device_id = NEW.device_id;

    IF parent_classified IN ('human', 'manual_override', 'migration_backfill') THEN
        IF current_user = 'device_service_ai' THEN
            RAISE EXCEPTION 'frozen_signals_ai: ai role cannot mutate signals of frozen device';
        END IF;
        override_token := current_setting('device_service.freeze_override', true);
        IF override_token IS NULL OR override_token = '' THEN
            RAISE EXCEPTION 'frozen_signals_ops: ops role must set freeze_override token';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS device_signals_freeze_check ON public.device_signals;
CREATE TRIGGER device_signals_freeze_check
    BEFORE INSERT OR UPDATE ON public.device_signals
    FOR EACH ROW EXECUTE FUNCTION public.enforce_signals_freeze();

COMMIT;
NOTIFY pgrst, 'reload schema';
