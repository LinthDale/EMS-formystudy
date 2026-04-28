-- Runs once on first container startup (when data volume is empty).
-- Creates: timescaledb extension, electricity_measurements hypertable, api schema + view,
-- and the two roles PostgREST needs.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ===== electricity_measurements: the time-series table =====
-- Columns match what Telegraf writes: time + device_id tag + 4 fields.
CREATE TABLE IF NOT EXISTS electricity_measurements (
    time       TIMESTAMPTZ       NOT NULL,
    device_id  TEXT              NOT NULL,
    voltage    DOUBLE PRECISION,
    current    DOUBLE PRECISION,
    power_kw   DOUBLE PRECISION,
    energy_kwh DOUBLE PRECISION
);

SELECT create_hypertable('electricity_measurements', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_electricity_device_time
    ON electricity_measurements (device_id, time DESC);

-- ===== PostgREST setup =====
-- PostgREST exposes one schema as a REST API.
-- We expose 'api' (views only) so internal tables stay hidden.
CREATE SCHEMA IF NOT EXISTS api;

CREATE OR REPLACE VIEW api.electricity_measurements AS
    SELECT time, device_id, voltage, current, power_kw, energy_kwh
    FROM public.electricity_measurements;

-- web_anon: the role HTTP requests appear as (read-only for now)
CREATE ROLE web_anon NOLOGIN;
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.electricity_measurements TO web_anon;

-- authenticator role is created in 02-authenticator.sh so its password can come
-- from the AUTHENTICATOR_PASSWORD env var (SQL files can't read env vars).
