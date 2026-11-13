-- Integration test; synthetic rows are rolled back.
BEGIN;
INSERT INTO public.electricity_measurements(time,device_id,power_kw,energy_kwh) VALUES
('2001-01-01T00:00:00Z','qa-history-001',10,20),
('2001-01-01T00:00:01Z','qa-history-001',100,21),
('2001-01-01T00:00:02Z','qa-history-001',NULL,22),
('2001-01-01T00:00:03Z','qa-history-001',999,23);
INSERT INTO public.factory_measurements(time,device_id,pump_on) VALUES
('2001-01-01T00:00:00Z','qa-history-001',false),
('2001-01-01T00:00:01Z','qa-history-001',true);
SET LOCAL ROLE web_anon;
DO $$
DECLARE h jsonb; p jsonb; v jsonb;
BEGIN
 h:=api.measurement_history('qa-history-001','electricity','2001-01-01Z','2001-01-01T00:00:03Z',3);
 SELECT x INTO v FROM jsonb_array_elements(h->'series') x WHERE x->>'signal'='power_kw';
 IF (v->>'value')::float8<>55 OR (v->>'min')::float8<>10 OR (v->>'max')::float8<>100
 OR (v->>'samples')::int<>2 OR (v->>'last')::float8<>100 THEN RAISE EXCEPTION 'aggregation failed %',v; END IF;
 h:=api.measurement_history('qa-history-001','factory','2001-01-01Z','2001-01-01T00:00:03Z',3);
 IF h->'series'->0->>'last'<>'1' OR h->'series'->0->>'min'<>'0' THEN RAISE EXCEPTION 'boolean failed'; END IF;
 p:=api.measurement_records('qa-history-001','electricity','2001-01-01Z','2001-01-01T00:00:03Z',2,0);
 IF jsonb_array_length(p->'rows')<>2 OR NOT (p->>'has_more')::boolean THEN RAISE EXCEPTION 'page 1 failed'; END IF;
 p:=api.measurement_records('qa-history-001','electricity','2001-01-01Z','2001-01-01T00:00:03Z',2,2);
 IF jsonb_array_length(p->'rows')<>1 OR (p->>'has_more')::boolean THEN RAISE EXCEPTION 'page 2 failed'; END IF;
 BEGIN
  PERFORM api.measurement_history('qa-history-001','electricity','2001-01-01Z','2001-02-01Z',60);
  RAISE EXCEPTION 'range cap missing';
 EXCEPTION WHEN invalid_parameter_value THEN NULL;
 END;
 IF jsonb_array_length(api.measurement_history('qa-no-data','factory','2001-01-01Z','2001-01-01T00:00:03Z',3)->'series')<>0 THEN RAISE EXCEPTION 'empty failed'; END IF;
END $$;
ROLLBACK;
