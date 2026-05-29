-- Migration: 008_backfill_existing_devices
-- PRD-0003 §7.5 / FR-315 — 把 PRD-0001/0002 既有 3 裝置登錄為 confirmed，
-- classified_by='migration_backfill'（屬凍結集合，AI 不得 mutate，見 ADR-015/016）。
-- 對應 active signals 一併寫入。device_type 依 PRD §7.5（plc-001 用 unknown）。
-- Idempotent：devices 用 ON CONFLICT DO NOTHING；signals 用 WHERE NOT EXISTS 守衛。
BEGIN;

INSERT INTO public.devices
    (device_id, device_type, status, protocol, gateway_id, classified_by, confirmed_at, last_seen_at)
VALUES
    ('sim-001',    'electricity', 'confirmed', 'modbus_tcp', 'ems-gateway', 'migration_backfill', now(), now()),
    ('plc-001',    'unknown',     'confirmed', 'modbus_tcp', 'kc-gateway',  'migration_backfill', now(), now()),
    ('sensor-001', 'temperature', 'confirmed', 'mqtt_json',  'kc-ingest',   'migration_backfill', now(), now())
ON CONFLICT (device_id) DO NOTHING;

-- 對應 signals（status='active'）。每列以 NOT EXISTS 守衛，重複執行不重插、不違反 partial unique index。
INSERT INTO public.device_signals (device_id, signal_name, unit, datatype, direction, source_ref, status, confirmed_by_ai)
SELECT v.device_id, v.signal_name, v.unit, v.datatype, v.direction, v.source_ref, 'active', FALSE
FROM (VALUES
    -- sim-001 (electricity)
    ('sim-001',    'voltage',     'V',       'float', 'read', 'modbus:holding:0'),
    ('sim-001',    'current',     'A',       'float', 'read', 'modbus:holding:1'),
    ('sim-001',    'power_kw',    'kW',      'float', 'read', 'modbus:holding:2'),
    ('sim-001',    'energy_kwh',  'kWh',     'float', 'read', 'modbus:holding:4'),
    -- plc-001 (PLC, unknown)
    ('plc-001',    'temperature', 'degC',    'float', 'read', 'modbus:holding:0'),
    ('plc-001',    'humidity',    '%RH',     'float', 'read', 'modbus:holding:2'),
    ('plc-001',    'motor_speed', 'RPM',     'float', 'read', 'modbus:holding:4'),
    ('plc-001',    'pressure',    'kPa',     'float', 'read', 'modbus:input:0'),
    ('plc-001',    'pump_on',     'boolean', 'bool',  'read', 'modbus:coil:0'),
    ('plc-001',    'valve_open',  'boolean', 'bool',  'read', 'modbus:coil:1'),
    -- sensor-001 (temperature)
    ('sensor-001', 'temperature', 'degC',    'float', 'read', 'mqtt:factory/sensor/temp_01'),
    ('sensor-001', 'humidity',    '%RH',     'float', 'read', 'mqtt:factory/sensor/temp_01')
) AS v(device_id, signal_name, unit, datatype, direction, source_ref)
WHERE EXISTS (SELECT 1 FROM public.devices d WHERE d.device_id = v.device_id)
  AND NOT EXISTS (
      SELECT 1 FROM public.device_signals s
      WHERE s.device_id = v.device_id AND s.signal_name = v.signal_name AND s.status = 'active'
  );

COMMIT;
NOTIFY pgrst, 'reload schema';
