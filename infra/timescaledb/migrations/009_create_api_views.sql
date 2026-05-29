-- Migration: 009_create_api_views
-- PRD-0003 §7.4 — 對外 PostgREST view，嚴格白名單欄位（禁 SELECT *，見 ADR-005/011）。
-- 只曝 status IN ('confirmed','active') 的 device；candidate/maintenance/retired 不對外。
-- Idempotent：CREATE OR REPLACE VIEW。
BEGIN;

-- api.devices：不曝 status / classified_by / ai_* / last_error / metadata / stale_marked_at
CREATE OR REPLACE VIEW api.devices AS
SELECT
    device_id,
    device_type,
    protocol,
    vendor,
    model,
    location,
    gateway_id,
    created_at,
    updated_at,
    last_seen_at,
    confirmed_at,
    activated_at
FROM public.devices
WHERE status IN ('confirmed', 'active');

GRANT SELECT ON api.devices TO web_anon;

-- api.device_signals：不曝 source_ref（OT 偵察情報）/ status / retired_at / confirmed_by_ai / metadata
CREATE OR REPLACE VIEW api.device_signals AS
SELECT
    s.id,
    s.device_id,
    s.signal_name,
    s.unit,
    s.datatype,
    s.direction,
    s.created_at,
    s.updated_at
FROM public.device_signals s
JOIN public.devices d USING (device_id)
WHERE s.status = 'active'
  AND d.status IN ('confirmed', 'active');

GRANT SELECT ON api.device_signals TO web_anon;

COMMIT;
NOTIFY pgrst, 'reload schema';
