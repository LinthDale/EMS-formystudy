"""Integration (real DB): FR-340 L2 guardrail budget is actually written to the
llm_budget_ledger as its OWN provider='guardrail' row, independent of the L1 row.

classify_under_budget is driven with a FAKE L1 provider + a metered fake guardrail (no real LLM
calls), but a REAL Database (AI/OPS pools) so the reserve/settle SQL hits the live ledger table.
Skips if the DB / roles are unreachable. Snapshots and restores the touched ledger rows so the
shared monthly ledger is left exactly as it was found.
"""
import os

import asyncpg
import pytest

pytestmark = pytest.mark.integration

_PRE = {"input_tokens": 50, "output_tokens": 5}
_POST = {"input_tokens": 40, "output_tokens": 4}
_EXP_IN, _EXP_OUT = 90, 9   # pre+post


def _settings():
    from device_service.config import Settings
    return Settings(
        _env_file=None,
        llm_provider="openai", llm_model="gpt-4o-mini", llm_monthly_budget_usd=100000.0,
        guardrail_provider="openai", guardrail_model="gpt-4o-mini",
        guardrail_monthly_budget_usd=100000.0,
        db_host=os.getenv("EMS_DB_HOST", "timescaledb"),
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"))


def _classifier():
    from device_service.classifier import Classifier
    from device_service.llm.guardrail import GuardrailVerdict
    from device_service.llm.types import ClassificationResult, SignalSuggestion

    class _Prov:
        name = "openai"

        async def classify_device(self, device_id, topic, sanitized):
            return ClassificationResult(
                "electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 0.95, "ok",
                {"usage": {"input_tokens": 100, "output_tokens": 20}})

    class _Guard:
        name = "llm_guardrail"

        async def check_input(self, sanitized, rendered):
            return GuardrailVerdict("pass", usage=dict(_PRE))

        async def check_output(self, sanitized, l1, rendered):
            return GuardrailVerdict("pass", usage=dict(_POST))

    return Classifier(_Prov(), _Guard(), model="gpt-4o-mini")


def _sample():
    from device_service.sanitizer import sanitize
    return sanitize("itest-gledger-1", "ems/devices/itest-gledger-1/measurements", "ilp",
                    [{"voltage": 220.0, "current": 1.1, "power_kw": 0.2}])


async def _su():
    try:
        return await asyncpg.connect(
            host=os.getenv("EMS_DB_HOST", "timescaledb"), database="ems",
            user="postgres", password=os.getenv("POSTGRES_PASSWORD", "postgres"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"superuser DB connection unavailable: {exc}")


async def _row(su, provider, period_start):
    return await su.fetchrow(
        "SELECT tokens_in, tokens_out, cost_usd FROM public.llm_budget_ledger "
        "WHERE provider=$1 AND period_start=$2", provider, period_start)


async def test_guardrail_budget_writes_own_ledger_row():
    from device_service.budget_ledger import current_period
    from device_service.db import Database
    from device_service.discovery_pipeline import GUARDRAIL_PROVIDER_KEY, classify_under_budget

    settings = _settings()
    period_start, _ = current_period()
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable / roles not set: {exc}")

    su = await _su()
    # snapshot the two rows we will touch so we can restore the shared ledger exactly
    before_g = await _row(su, GUARDRAIL_PROVIDER_KEY, period_start)
    before_l1 = await _row(su, "openai", period_start)
    try:
        await classify_under_budget(
            db, _classifier(), settings, sanitized=_sample(), default_device_type="unknown",
            latest_correction_device_type=None, applied_ids=(), device_id="itest-gledger-1",
            first_seen="")

        after_g = await _row(su, GUARDRAIL_PROVIDER_KEY, period_start)
        assert after_g is not None, "FR-340: a provider='guardrail' ledger row must exist"
        d_in = after_g["tokens_in"] - (before_g["tokens_in"] if before_g else 0)
        d_out = after_g["tokens_out"] - (before_g["tokens_out"] if before_g else 0)
        assert (d_in, d_out) == (_EXP_IN, _EXP_OUT)        # actual pre+post usage was settled
        assert after_g["cost_usd"] >= (before_g["cost_usd"] if before_g else 0)
        # independence: the L1 row is a SEPARATE row, not merged with guardrail's
        after_l1 = await _row(su, "openai", period_start)
        assert after_l1 is not None
    finally:
        # restore both rows to their pre-test state (delete if they did not exist before)
        for provider, before in ((GUARDRAIL_PROVIDER_KEY, before_g), ("openai", before_l1)):
            if before is None:
                await su.execute("DELETE FROM public.llm_budget_ledger WHERE provider=$1 AND period_start=$2",
                                 provider, period_start)
            else:
                await su.execute(
                    "UPDATE public.llm_budget_ledger SET tokens_in=$3, tokens_out=$4, cost_usd=$5 "
                    "WHERE provider=$1 AND period_start=$2",
                    provider, period_start, before["tokens_in"], before["tokens_out"], before["cost_usd"])
        await su.close()
        await db.close()
