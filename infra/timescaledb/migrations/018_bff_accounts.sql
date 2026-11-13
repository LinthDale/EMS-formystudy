-- PRD-0023 / ADR-035. Run as DB migration owner. Idempotent; no user seeds.
BEGIN;
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bff_auth_owner') THEN
    CREATE ROLE bff_auth_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bff_auth_reader') THEN
    CREATE ROLE bff_auth_reader NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bff_auth_admin') THEN
    CREATE ROLE bff_auth_admin NOLOGIN;
  END IF;
END $roles$;
CREATE SCHEMA IF NOT EXISTS bff_auth AUTHORIZATION bff_auth_owner;
REVOKE ALL ON SCHEMA bff_auth FROM PUBLIC;
CREATE TABLE IF NOT EXISTS bff_auth.accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE CHECK (username ~ '^[a-zA-Z0-9_.-]{1,64}$'),
  password_hash text NOT NULL CHECK (length(password_hash) BETWEEN 40 AND 512),
  role text NOT NULL CHECK (role IN ('ops','ingest','readonly')),
  enabled boolean NOT NULL DEFAULT true,
  auth_version bigint NOT NULL DEFAULT 1 CHECK (auth_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bff_auth.account_audit (
  request_id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,
  account_id uuid NOT NULL REFERENCES bff_auth.accounts(id),
  username text NOT NULL,
  action text NOT NULL,
  reason text NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 500),
  before_state jsonb,
  after_state jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS account_audit_user_time
  ON bff_auth.account_audit(username, created_at DESC);
CREATE TABLE IF NOT EXISTS bff_auth.imports (
  source text PRIMARY KEY,
  imported_at timestamptz NOT NULL DEFAULT now(),
  account_count integer NOT NULL
);
CREATE OR REPLACE VIEW bff_auth.account_summary AS
  SELECT id,username,role,enabled,auth_version,created_at,updated_at FROM bff_auth.accounts;

CREATE OR REPLACE FUNCTION bff_auth.safe_phc(p_hash text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $body$
DECLARE parts text[]; segment text; decoded bytea;
BEGIN
  IF p_hash IS NULL OR length(p_hash)>512 THEN RETURN false; END IF;
  FOREACH segment IN ARRAY ARRAY[split_part(p_hash,'$',5),split_part(p_hash,'$',6)] LOOP
    decoded := decode(segment || repeat('=',(4-length(segment)%4)%4),'base64');
    IF rtrim(replace(encode(decoded,'base64'),chr(10),''),'=') <> segment THEN
      RETURN false;
    END IF;
  END LOOP;
  parts := regexp_match(p_hash,
    '^\$argon2id\$v=19\$m=([0-9]{1,6}),t=([0-9]{1,2}),p=([0-9]{1,2})\$[A-Za-z0-9+/]{11,128}\$[A-Za-z0-9+/]{6,128}$');
  RETURN COALESCE(parts IS NOT NULL AND parts[1]::int BETWEEN 8 AND 262144
    AND parts[2]::int BETWEEN 1 AND 10 AND parts[3]::int BETWEEN 1 AND 16
    AND parts[1]::int >= 8*parts[3]::int, false);
EXCEPTION WHEN invalid_parameter_value OR invalid_text_representation THEN RETURN false;
END $body$;

CREATE OR REPLACE FUNCTION bff_auth.manage_account(
  p_request_id uuid, p_action text, p_username text,
  p_hash text, p_role text, p_reason text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $body$
DECLARE old_row bff_auth.accounts%ROWTYPE;
        new_row bff_auth.accounts%ROWTYPE;
        previous bff_auth.account_audit%ROWTYPE;
        before_json jsonb; after_json jsonb;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'account management requires READ COMMITTED';
  END IF;
  PERFORM pg_advisory_xact_lock(230035);
  IF p_request_id IS NULL OR p_username IS NULL OR p_username !~ '^[a-zA-Z0-9_.-]{1,64}$'
     OR p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 500
     OR p_action IS NULL OR p_action NOT IN ('create','enable','disable','set-role','reset-password','import') THEN
    RAISE EXCEPTION 'invalid account operation';
  END IF;
  SELECT * INTO previous FROM bff_auth.account_audit WHERE request_id=p_request_id;
  IF FOUND THEN
    IF previous.username<>p_username OR previous.action<>p_action OR previous.reason<>p_reason
       OR (p_role IS NOT NULL AND previous.after_state->>'role'<>p_role) THEN
      RAISE EXCEPTION 'request_id conflict';
    END IF;
    RETURN previous.after_state;
  END IF;
  IF p_action IN ('create','import','reset-password') AND NOT bff_auth.safe_phc(p_hash) THEN
    RAISE EXCEPTION 'invalid password hash';
  END IF;
  IF p_action IN ('create','import','set-role') AND
     (p_role IS NULL OR p_role NOT IN ('ops','ingest','readonly')) THEN
    RAISE EXCEPTION 'invalid account role';
  END IF;
  SELECT * INTO old_row FROM bff_auth.accounts WHERE username=p_username FOR UPDATE;
  IF p_action IN ('create','import') THEN
    IF old_row.id IS NOT NULL THEN RAISE EXCEPTION 'account already exists'; END IF;
    INSERT INTO bff_auth.accounts(username,password_hash,role)
      VALUES(p_username,p_hash,p_role) RETURNING * INTO new_row;
  ELSE
    IF old_row.id IS NULL THEN RAISE EXCEPTION 'account not found'; END IF;
    before_json := to_jsonb(old_row) - 'password_hash';
    UPDATE bff_auth.accounts SET
      password_hash=CASE WHEN p_action='reset-password' THEN p_hash ELSE password_hash END,
      role=CASE WHEN p_action='set-role' THEN p_role ELSE role END,
      enabled=CASE WHEN p_action='enable' THEN true WHEN p_action='disable' THEN false ELSE enabled END,
      auth_version=auth_version+1, updated_at=clock_timestamp()
      WHERE id=old_row.id RETURNING * INTO new_row;
  END IF;
  IF NOT EXISTS (SELECT FROM bff_auth.accounts WHERE enabled AND role='ops') THEN
    RAISE EXCEPTION 'at least one enabled OPS account is required';
  END IF;
  after_json := to_jsonb(new_row) - 'password_hash';
  INSERT INTO bff_auth.account_audit(request_id,actor,account_id,username,action,reason,before_state,after_state)
    VALUES(p_request_id,session_user,new_row.id,p_username,p_action,p_reason,before_json,after_json);
  RETURN after_json;
END $body$;

CREATE OR REPLACE FUNCTION bff_auth.import_legacy(p_records jsonb, p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $body$
DECLARE rec jsonb; imported integer:=0;
BEGIN
  IF current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'account management requires READ COMMITTED';
  END IF;
  PERFORM pg_advisory_xact_lock(230035);
  IF EXISTS (SELECT FROM bff_auth.imports WHERE source='legacy-env-v1') THEN
    RETURN jsonb_build_object('already_imported',true);
  END IF;
  IF p_records IS NULL OR jsonb_typeof(p_records)<>'array' OR jsonb_array_length(p_records) NOT BETWEEN 1 AND 1000 THEN
    RAISE EXCEPTION 'invalid legacy import';
  END IF;
  -- Bootstrap OPS first; every account change shares the outer transaction.
  FOR rec IN SELECT value FROM jsonb_array_elements(p_records)
             ORDER BY CASE WHEN value->>'role'='ops' THEN 0 ELSE 1 END LOOP
    PERFORM bff_auth.manage_account(gen_random_uuid(),'import',rec->>'username',
      rec->>'password_hash',rec->>'role',p_reason);
    imported:=imported+1;
  END LOOP;
  INSERT INTO bff_auth.imports(source,account_count) VALUES('legacy-env-v1',imported);
  RETURN jsonb_build_object('imported',imported,'already_imported',false);
END $body$;

CREATE OR REPLACE FUNCTION bff_auth.reject_audit_change()
RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $body$
BEGIN RAISE EXCEPTION 'account audit is append only'; END $body$;
DROP TRIGGER IF EXISTS account_audit_immutable ON bff_auth.account_audit;
CREATE TRIGGER account_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
  ON bff_auth.account_audit FOR EACH STATEMENT EXECUTE FUNCTION bff_auth.reject_audit_change();

ALTER TABLE bff_auth.accounts OWNER TO bff_auth_owner;
ALTER TABLE bff_auth.account_audit OWNER TO bff_auth_owner;
ALTER TABLE bff_auth.imports OWNER TO bff_auth_owner;
ALTER VIEW bff_auth.account_summary OWNER TO bff_auth_owner;
ALTER FUNCTION bff_auth.safe_phc(text) OWNER TO bff_auth_owner;
ALTER FUNCTION bff_auth.manage_account(uuid,text,text,text,text,text) OWNER TO bff_auth_owner;
ALTER FUNCTION bff_auth.import_legacy(jsonb,text) OWNER TO bff_auth_owner;
ALTER FUNCTION bff_auth.reject_audit_change() OWNER TO bff_auth_owner;
REVOKE ALL ON ALL TABLES IN SCHEMA bff_auth FROM PUBLIC,bff_auth_reader,bff_auth_admin;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bff_auth FROM PUBLIC,bff_auth_reader,bff_auth_admin;
GRANT USAGE ON SCHEMA bff_auth TO bff_auth_reader,bff_auth_admin;
GRANT SELECT ON bff_auth.accounts TO bff_auth_reader;
GRANT SELECT ON bff_auth.account_summary,bff_auth.account_audit TO bff_auth_admin;
GRANT EXECUTE ON FUNCTION bff_auth.manage_account(uuid,text,text,text,text,text),
  bff_auth.import_legacy(jsonb,text) TO bff_auth_admin;
COMMIT;
