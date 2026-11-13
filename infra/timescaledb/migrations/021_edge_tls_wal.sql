-- ADR-050: a named synchronous peer must also have a certificate TLS channel.
BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='ems_wal_archive') THEN
        CREATE ROLE ems_wal_archive NOLOGIN REPLICATION;
    END IF;
END $$;
CREATE OR REPLACE FUNCTION edge_ingest.sync_tls_wal_flushed(peer text, target pg_lsn DEFAULT NULL)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$
 SELECT current_setting('fsync') = 'on'
    AND current_setting('synchronous_commit') = 'on'
    AND regexp_replace(current_setting('synchronous_standby_names'), '\s', '', 'g')
        = 'FIRST1(' || peer || ')'
    AND NOT pg_is_in_recovery()
    AND (SELECT count(*) = 1 AND bool_and(r.state = 'streaming' AND r.sync_state = 'sync'
          AND r.flush_lsn IS NOT NULL AND (target IS NULL OR r.flush_lsn >= target)
          AND s.ssl AND NULLIF(s.client_dn,'') IS NOT NULL AND r.usename='ems_wal_archive')
         FROM pg_stat_replication r LEFT JOIN pg_stat_ssl s ON s.pid=r.pid
         WHERE r.application_name = peer)
$$;
ALTER FUNCTION edge_ingest.sync_tls_wal_flushed(text,pg_lsn) OWNER TO postgres;
REVOKE ALL ON FUNCTION edge_ingest.sync_tls_wal_flushed(text,pg_lsn) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_ingest.sync_tls_wal_flushed(text,pg_lsn) TO ems_edge_receiver;
-- Existing callers receive the stronger policy too. New code calls the new
-- name directly, so a missing 021 or accidental 020 rerun cannot downgrade it.
CREATE OR REPLACE FUNCTION edge_ingest.sync_wal_flushed(peer text, target pg_lsn DEFAULT NULL)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
AS $$ SELECT edge_ingest.sync_tls_wal_flushed(peer,target) $$;
ALTER FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) OWNER TO postgres;
REVOKE ALL ON FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) TO ems_edge_receiver;
COMMIT;
