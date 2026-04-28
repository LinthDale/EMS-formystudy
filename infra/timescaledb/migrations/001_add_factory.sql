-- Migration: 001_add_factory
-- 新增 factory_measurements 表（PLC + Sensor 資料），與 electricity_measurements 並存
-- Idempotent — 重複執行安全
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'factory_measurements') THEN
        RAISE NOTICE 'factory_measurements already exists, skipping';
        RETURN;
    END IF;

    CREATE TABLE factory_measurements (
        time        TIMESTAMPTZ      NOT NULL,
        device_id   TEXT             NOT NULL,
        device_type TEXT,
        temperature DOUBLE PRECISION,
        humidity    DOUBLE PRECISION,
        motor_speed DOUBLE PRECISION,
        pump_on     BOOLEAN,
        valve_open  BOOLEAN,
        pressure    DOUBLE PRECISION
    );

    PERFORM create_hypertable('factory_measurements', 'time', if_not_exists => TRUE);
    CREATE INDEX idx_factory_device_time ON factory_measurements (device_id, time DESC);

    CREATE VIEW api.factory_measurements AS
        SELECT time, device_id, device_type,
               temperature, humidity, motor_speed,
               pump_on, valve_open, pressure
        FROM public.factory_measurements;

    GRANT SELECT ON api.factory_measurements TO web_anon;
    RAISE NOTICE 'factory_measurements created';
END $$;

COMMIT;
NOTIFY pgrst, 'reload schema';
