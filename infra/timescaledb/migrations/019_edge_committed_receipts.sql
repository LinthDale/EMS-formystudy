-- PRD-0021 / ADR-043. Additive and idempotent; never deduplicates legacy rows.
BEGIN;
CREATE SCHEMA IF NOT EXISTS edge_ingest;
REVOKE ALL ON SCHEMA edge_ingest FROM PUBLIC;
CREATE TABLE IF NOT EXISTS edge_ingest.receipts (
    gateway_id TEXT NOT NULL,
    sample_id UUID NOT NULL,
    device_id TEXT NOT NULL,
    stream_id UUID NOT NULL,
    capture_seq BIGINT NOT NULL CHECK (capture_seq > 0),
    window_id UUID NOT NULL,
    config_revision TEXT NOT NULL,
    payload_hash TEXT NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    sampled_at_us BIGINT NOT NULL CHECK (sampled_at_us > 0),
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    retention_until TIMESTAMPTZ NOT NULL,
    sample JSONB NOT NULL,
    PRIMARY KEY (gateway_id, sample_id),
    UNIQUE (gateway_id, device_id, stream_id, capture_seq)
);
CREATE INDEX IF NOT EXISTS edge_receipt_window
    ON edge_ingest.receipts(gateway_id, device_id, stream_id, window_id);
ALTER TABLE public.electricity_measurements ADD COLUMN IF NOT EXISTS edge_gateway_id TEXT;
ALTER TABLE public.electricity_measurements ADD COLUMN IF NOT EXISTS edge_sample_id UUID;
CREATE INDEX IF NOT EXISTS electricity_edge_identity
    ON public.electricity_measurements(edge_gateway_id, edge_sample_id, time);
-- Receipt row locks provide cross-time uniqueness; Timescale unique indexes must include time.
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='ems_edge_receiver') THEN
        CREATE ROLE ems_edge_receiver NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public, edge_ingest TO ems_edge_receiver;
GRANT SELECT, INSERT ON edge_ingest.receipts TO ems_edge_receiver;
-- SELECT FOR UPDATE requires UPDATE on at least one column; runtime never updates this column.
GRANT UPDATE (committed_at) ON edge_ingest.receipts TO ems_edge_receiver;
GRANT SELECT, INSERT ON public.electricity_measurements TO ems_edge_receiver;
COMMIT;
