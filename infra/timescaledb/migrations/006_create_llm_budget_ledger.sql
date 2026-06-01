-- Migration: 006_create_llm_budget_ledger
-- PRD-0003 §7.5 / §10 — LLM 預算帳本（fail-closed gate 依此判斷，見 ADR-014）。
-- L1 與 L2 guardrail 各自一個 provider row。Idempotent。
BEGIN;

CREATE TABLE IF NOT EXISTS public.llm_budget_ledger (
    id           BIGSERIAL     PRIMARY KEY,
    period_start TIMESTAMPTZ   NOT NULL,
    period_end   TIMESTAMPTZ   NOT NULL,
    provider     TEXT          NOT NULL,
    tokens_in    BIGINT        NOT NULL DEFAULT 0,
    tokens_out   BIGINT        NOT NULL DEFAULT 0,
    cost_usd     NUMERIC(10,4) NOT NULL DEFAULT 0,
    budget_usd   NUMERIC(10,4) NOT NULL,
    active       BOOLEAN       NOT NULL DEFAULT TRUE,
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (period_start, provider)
);

CREATE INDEX IF NOT EXISTS llm_budget_ledger_active ON public.llm_budget_ledger (active, provider);

COMMIT;
NOTIFY pgrst, 'reload schema';
