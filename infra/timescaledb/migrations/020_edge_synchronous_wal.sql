-- ADR-049: expose only a durability predicate, not replication statistics.
BEGIN;
CREATE OR REPLACE FUNCTION edge_ingest.sync_wal_flushed(peer text, target pg_lsn DEFAULT NULL)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$
 SELECT current_setting('fsync') = 'on'
    AND current_setting('synchronous_commit') = 'on'
    -- One required peer only: another ANY/FIRST candidate cannot substitute.
    AND regexp_replace(current_setting('synchronous_standby_names'), '\s', '', 'g')
        = 'FIRST1(' || peer || ')'
    AND NOT pg_is_in_recovery()
    AND (SELECT count(*) = 1 AND bool_and(state = 'streaming' AND sync_state = 'sync'
          AND flush_lsn IS NOT NULL AND (target IS NULL OR flush_lsn >= target))
         FROM pg_stat_replication WHERE application_name = peer)
$$;
ALTER FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) OWNER TO postgres;
REVOKE ALL ON FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_ingest.sync_wal_flushed(text,pg_lsn) TO ems_edge_receiver;
COMMIT;
