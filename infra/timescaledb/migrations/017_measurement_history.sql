-- PRD-0018 / ADR-027. 016 reserved for the narrow-table proposal.
-- Additive, idempotent, read-only functions on existing public measurement views.
BEGIN;
CREATE OR REPLACE FUNCTION api.measurement_history(
 p_device_id text, p_domain text, p_since timestamptz, p_until timestamptz, p_step_seconds integer
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public, api AS $$
DECLARE result jsonb;
BEGIN
 IF p_device_id IS NULL OR p_domain IS NULL OR p_since IS NULL OR p_until IS NULL OR p_step_seconds IS NULL
 OR p_device_id !~ '^[A-Za-z0-9_-]{1,64}$' OR p_domain NOT IN ('electricity','factory')
 OR NOT isfinite(p_since) OR NOT isfinite(p_until)
 OR p_until <= p_since OR p_until-p_since > interval '7 days'
 OR p_step_seconds < 1 OR p_step_seconds > 604800
 OR extract(epoch FROM p_until-p_since)/p_step_seconds > 1200 THEN
  RAISE EXCEPTION 'Invalid bounded history request' USING ERRCODE='22023';
 END IF;
 WITH source AS (
  SELECT m.time, v.signal, v.value
  FROM api.electricity_measurements m
  CROSS JOIN LATERAL (VALUES ('voltage',m.voltage),('current',m.current),
    ('power_kw',m.power_kw),('energy_kwh',m.energy_kwh)) v(signal,value)
  WHERE p_domain='electricity' AND m.device_id=p_device_id AND m.time>=p_since AND m.time<p_until
  UNION ALL
  SELECT m.time, v.signal, v.value
  FROM api.factory_measurements m
  CROSS JOIN LATERAL (VALUES ('temperature',m.temperature),('humidity',m.humidity),
    ('motor_speed',m.motor_speed),('pressure',m.pressure),
    ('pump_on',m.pump_on::integer::double precision),('valve_open',m.valve_open::integer::double precision)) v(signal,value)
  WHERE p_domain='factory' AND m.device_id=p_device_id AND m.time>=p_since AND m.time<p_until
 ), grouped AS (
  SELECT date_bin(make_interval(secs=>p_step_seconds),time,p_since) AS time,
   signal, avg(value) AS value, min(value) AS min, max(value) AS max,
   (array_agg(value ORDER BY time DESC,value DESC))[1] AS last,
   count(*) AS samples,max(time) AS last_time
  FROM source WHERE value IS NOT NULL AND value NOT IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)
  GROUP BY 1,signal
 )
 SELECT coalesce(jsonb_agg(to_jsonb(g) ORDER BY g.time,g.signal),'[]'::jsonb) INTO result FROM grouped g;
 RETURN jsonb_build_object('device_id',p_device_id,'since',p_since,'until',p_until,
   'bucket_seconds',p_step_seconds,'series',result);
END $$;
REVOKE ALL ON FUNCTION api.measurement_history(text,text,timestamptz,timestamptz,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.measurement_history(text,text,timestamptz,timestamptz,integer) TO web_anon;

CREATE OR REPLACE FUNCTION api.measurement_records(
 p_device_id text, p_domain text, p_since timestamptz, p_until timestamptz, p_limit integer, p_offset integer
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public, api AS $$
DECLARE result jsonb; more boolean;
BEGIN
 IF p_device_id IS NULL OR p_domain IS NULL OR p_since IS NULL OR p_until IS NULL OR p_limit IS NULL OR p_offset IS NULL
 OR p_device_id !~ '^[A-Za-z0-9_-]{1,64}$' OR p_domain NOT IN ('electricity','factory')
 OR NOT isfinite(p_since) OR NOT isfinite(p_until) OR p_until<=p_since OR p_until-p_since>interval '7 days'
 OR p_limit<1 OR p_limit>1000 OR p_offset<0 OR p_offset>1000000 THEN
  RAISE EXCEPTION 'Invalid bounded records request' USING ERRCODE='22023';
 END IF;
 WITH source AS (
  SELECT m.time, to_jsonb(m) AS row FROM api.electricity_measurements m
  WHERE p_domain='electricity' AND m.device_id=p_device_id AND m.time>=p_since AND m.time<p_until
  UNION ALL
  SELECT m.time, to_jsonb(m) AS row FROM api.factory_measurements m
  WHERE p_domain='factory' AND m.device_id=p_device_id AND m.time>=p_since AND m.time<p_until
 ), page AS (
  SELECT * FROM source ORDER BY time DESC,row DESC LIMIT p_limit+1 OFFSET p_offset
 ), numbered AS (
  SELECT *,row_number() OVER (ORDER BY time DESC,row DESC) AS n FROM page
 )
 SELECT coalesce(jsonb_agg(row ORDER BY n) FILTER (WHERE n<=p_limit),'[]'::jsonb),count(*)>p_limit
 INTO result,more FROM numbered;
 RETURN jsonb_build_object('rows',result,'has_more',more);
END $$;
REVOKE ALL ON FUNCTION api.measurement_records(text,text,timestamptz,timestamptz,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api.measurement_records(text,text,timestamptz,timestamptz,integer,integer) TO web_anon;
COMMIT;
NOTIFY pgrst,'reload schema';
