-- Migration: 000_rename_measurements
-- 將 measurements → electricity_measurements，與 factory_measurements 對稱。
-- Idempotent — 重複執行安全；全新部署（init.sql 已建新表）也安全跳過。
BEGIN;

DO $$
BEGIN
    -- 已是新名字 → 跳過（重複執行）
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='public' AND table_name='electricity_measurements') THEN
        RAISE NOTICE 'electricity_measurements already exists, skipping rename';
        RETURN;
    END IF;

    -- 找不到舊表 → 跳過（全新部署，init.sql 直接建好新表）
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name='measurements') THEN
        RAISE NOTICE 'measurements not found (fresh install), skipping';
        RETURN;
    END IF;

    -- 1. Rename table（hypertable metadata 自動跟著）
    ALTER TABLE public.measurements RENAME TO electricity_measurements;

    -- 2. Rename index
    ALTER INDEX IF EXISTS idx_measurements_device_time
          RENAME TO idx_electricity_device_time;

    -- 3. Replace API view
    DROP VIEW IF EXISTS api.measurements;
    CREATE VIEW api.electricity_measurements AS
        SELECT time, device_id, voltage, current, power_kw, energy_kwh
        FROM public.electricity_measurements;
    GRANT SELECT ON api.electricity_measurements TO web_anon;

    RAISE NOTICE 'Renamed measurements -> electricity_measurements (data preserved)';
END $$;

COMMIT;
NOTIFY pgrst, 'reload schema';
