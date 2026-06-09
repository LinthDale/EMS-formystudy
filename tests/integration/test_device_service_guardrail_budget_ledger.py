"""Integration (real DB): FR-340 L2 guardrail budget against the live llm_budget_ledger.

Two cases, both driving classify_under_budget with a FAKE L1 provider + a metered fake guardrail
(no real LLM calls) but a REAL Database (AI/OPS pools) so the reserve/settle SQL hits the live
ledger:
  1. happy path  -> a provider='guardrail' row is written with the actual pre+post token usage,
                    independent of the L1 'openai' row.
  2. budget 100% -> the guardrail reserve is DENIED, classification stops entirely (neither L1 nor
                    L2 is called) and falls back; the L1 reservation is taken then refunded (no
                    net spend). FR-340 fail-closed.

Skips if the DB / roles are unreachable. Snapshots and restores every touched ledger row so the
shared monthly ledger is left exactly as found.
"""
import os

import asyncpg
import pytest

pytestmark = pytest.mark.integration

_PRE = {"input_tokens": 50, "output_tokens": 5}
_POST = {"input_tokens": 40, "output_tokens": 4}
_EXP_IN, _EXP_OUT = 90, 9   # pre + post


class _Prov:
    name = "openai"

    def __init__(self):
        self.calls = 0

    async def classify_device(self, device_id, topic, sanitized):
        self.calls += 1
        from device_service.llm.types import ClassificationResult, SignalSuggestion
        return ClassificationResult(
            "electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 0.95, "ok",
            {"usage": {"input_tokens": 100, "output_tokens": 20}})


class _Guard:
    name = "llm_guardrail"

    def __init__(self):
        self.calls = 0

    async def check_input(self, sanitized, rendered):
        self.calls += 1
        from device_service.llm.guardrail import GuardrailVerdict
        return GuardrailVerdict("pass", usage=dict(_PRE))

    async def check_output(self, sanitized, l1, rendered):
        self.calls += 1
        from device_service.llm.guardrail import GuardrailVerdict
        return GuardrailVerdict("pass", usage=dict(_POST))


def _settings(*, guardrail_budget=100000.0):
    from device_service.config import Settings
    return Settings(
        _env_file=None,
        llm_provider="openai", llm_model="gpt-4o-mini", llm_monthly_budget_usd=100000.0,
        guardrail_provider="openai", guardrail_model="gpt-4o-mini",
        guardrail_monthly_budget_usd=guardrail_budget,
        db_host=os.getenv("EMS_DB_HOST", "timescaledb"),
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"))


def _clf():
    from device_service.classifier import Classifier
    prov, guard = _Prov(), _Guard()
    return Classifier(prov, guard, model="gpt-4o-mini"), prov, guard


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


async def _connect(settings):
    from device_service.db import Database
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable / roles not set: {exc}")
    return db


async def _restore(su, period_start, snapshots):
    """Put every touched (provider -> row|None) back exactly as it was."""
    for provider, before in snapshots.items():
        if before is None:
            await su.execute("DELETE FROM public.llm_budget_ledger WHERE provider=$1 AND period_start=$2",
                             provider, period_start)
        else:
            await su.execute(
                "UPDATE public.llm_budget_ledger SET tokens_in=$3, tokens_out=$4, cost_usd=$5 "
                "WHERE provider=$1 AND period_start=$2",
                provider, period_start, before["tokens_in"], before["tokens_out"], before["cost_usd"])


async def test_guardrail_budget_writes_own_ledger_row():
    from device_service.budget_ledger import current_period
    from device_service.discovery_pipeline import GUARDRAIL_PROVIDER_KEY, classify_under_budget

    settings = _settings()
    period_start, _ = current_period()
    db = await _connect(settings)
    su = await _su()
    before = {GUARDRAIL_PROVIDER_KEY: await _row(su, GUARDRAIL_PROVIDER_KEY, period_start),
              "openai": await _row(su, "openai", period_start)}
    try:
        clf, prov, guard = _clf()
        await classify_under_budget(
            db, clf, settings, sanitized=_sample(), default_device_type="unknown",
            latest_correction_device_type=None, applied_ids=(), device_id="itest-gledger-1", first_seen="")
        assert prov.calls == 1 and guard.calls == 2   # L1 once, guardrail pre+post

        after_g = await _row(su, GUARDRAIL_PROVIDER_KEY, period_start)
        assert after_g is not None, "FR-340: a provider='guardrail' ledger row must exist"
        bg = before[GUARDRAIL_PROVIDER_KEY]
        d_in = after_g["tokens_in"] - (bg["tokens_in"] if bg else 0)
        d_out = after_g["tokens_out"] - (bg["tokens_out"] if bg else 0)
        assert (d_in, d_out) == (_EXP_IN, _EXP_OUT)        # actual pre+post usage settled
        assert after_g["cost_usd"] >= (bg["cost_usd"] if bg else 0)
        assert await _row(su, "openai", period_start) is not None   # L1 is a SEPARATE row
    finally:
        await _restore(su, period_start, before)
        await su.close()
        await db.close()


async def test_guardrail_budget_exhausted_falls_back_and_spends_nothing():
    from device_service.budget_ledger import current_period
    from device_service.discovery_pipeline import GUARDRAIL_PROVIDER_KEY, classify_under_budget

    settings = _settings(guardrail_budget=1e-9)   # any reserve exceeds the cap -> DENIED
    period_start, _ = current_period()
    db = await _connect(settings)
    su = await _su()
    before = {GUARDRAIL_PROVIDER_KEY: await _row(su, GUARDRAIL_PROVIDER_KEY, period_start),
              "openai": await _row(su, "openai", period_start)}
    try:
        clf, prov, guard = _clf()
        out = await classify_under_budget(
            db, clf, settings, sanitized=_sample(), default_device_type="unknown",
            latest_correction_device_type=None, applied_ids=(), device_id="itest-gledger-1", first_seen="")
        # FR-340 fail-closed: classification stops entirely, falls back
        assert out.summary_source == "system_fallback"
        assert out.last_error == "guardrail_budget_exhausted"
        assert prov.calls == 0 and guard.calls == 0       # neither L1 nor L2 ran

        # guardrail reserve was DENIED -> row unchanged (no spend)
        bg = before[GUARDRAIL_PROVIDER_KEY]
        after_g = await _row(su, GUARDRAIL_PROVIDER_KEY, period_start)
        g_cost = (after_g["cost_usd"] if after_g else 0)
        assert g_cost == (bg["cost_usd"] if bg else 0)
        # L1 reserve was taken then refunded on the fallback -> net cost unchanged
        bl = before["openai"]
        after_l1 = await _row(su, "openai", period_start)
        l1_cost = (after_l1["cost_usd"] if after_l1 else 0)
        assert abs(float(l1_cost) - float(bl["cost_usd"] if bl else 0)) < 1e-9
    finally:
        await _restore(su, period_start, before)
        await su.close()
        await db.close()
