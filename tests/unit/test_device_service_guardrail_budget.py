"""Unit: FR-340 L2 guardrail budget reserve/settle wiring in classify_under_budget.

No DB — budget_reserve / budget_settle / persist_outcome are monkeypatched to record calls,
so this verifies the SEPARATE provider='guardrail' reservation, the settle with the actual
pre+post usage, and the fail-closed gate (guardrail budget exhausted -> L1 also stops)."""
import pytest

from device_service import discovery_pipeline as dp
from device_service.classifier import Classifier
from device_service.llm.guardrail import GuardrailVerdict
from device_service.llm.types import ClassificationResult, SignalSuggestion
from device_service.sanitizer import sanitize


class _FakeConn:
    pass


class _FakeTx:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, *a):
        return False


class _FakeDB:
    def ai_tx(self, lock=None):
        return _FakeTx()


class _Settings:
    llm_provider = "openai"
    llm_model = "gpt-4o-mini"
    llm_pricing_json = ""
    llm_reserve_input_tokens = 4000
    llm_max_output_tokens = 1024
    llm_monthly_budget_usd = 20.0
    guardrail_provider = "openai"
    guardrail_model = "gpt-4o-mini"
    guardrail_default_model_openai = "gpt-4o-mini"
    guardrail_max_output_tokens = 256
    guardrail_reserve_input_tokens = 8000
    guardrail_monthly_budget_usd = 10.0


class _Prov:
    name = "openai"

    def __init__(self):
        self.calls = 0

    async def classify_device(self, device_id, topic, sanitized):
        self.calls += 1
        return ClassificationResult(
            "electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 0.95, "ok",
            {"usage": {"input_tokens": 100, "output_tokens": 20}})


class _Guard:
    name = "llm_guardrail"

    async def check_input(self, sanitized, rendered):
        return GuardrailVerdict("pass", usage={"input_tokens": 50, "output_tokens": 5})

    async def check_output(self, sanitized, l1, rendered):
        return GuardrailVerdict("pass", usage={"input_tokens": 40, "output_tokens": 4})


def _sample():
    return sanitize("d1", "ems/devices/d1/measurements", "ilp", [{"voltage": 220.0}])


@pytest.fixture
def patched(monkeypatch):
    reserves, settles = [], []
    state = {"allow": lambda provider: True}

    async def fake_reserve(conn, provider, ps, pe, est, budget):
        reserves.append((provider, round(est, 8)))
        return state["allow"](provider)

    async def fake_settle(conn, provider, ps, est, model, tin, tout, pricing=None):
        settles.append((provider, tin, tout))
        return 0.0

    async def fake_persist(conn, *, device_id, outcome, applied_ids):
        return None

    monkeypatch.setattr(dp, "budget_reserve", fake_reserve)
    monkeypatch.setattr(dp, "budget_settle", fake_settle)
    monkeypatch.setattr(dp, "persist_outcome", fake_persist)
    return reserves, settles, state


async def _classify(prov, guard):
    return await dp.classify_under_budget(
        _FakeDB(), Classifier(prov, guard, model="gpt-4o-mini"), _Settings(),
        sanitized=_sample(), default_device_type="unknown", latest_correction_device_type=None,
        applied_ids=(), device_id="d1", first_seen="")


async def test_guardrail_reserved_and_settled_separately(patched):
    reserves, settles, _ = patched
    prov = _Prov()
    out = await _classify(prov, _Guard())
    assert out.summary_source == "llm"
    # both L1 and L2 get their OWN reservation row
    assert {p for p, _ in reserves} == {"openai", "guardrail"}
    # guardrail settles the ACTUAL pre+post token usage (50+40 / 5+4)
    assert ("guardrail", 90, 9) in settles


async def test_guardrail_budget_exhausted_stops_l1_and_falls_back(patched):
    reserves, settles, state = patched
    state["allow"] = lambda provider: provider != "guardrail"   # L1 ok, guardrail denied
    prov = _Prov()
    out = await _classify(prov, _Guard())
    assert out.summary_source == "system_fallback" and out.last_error == "guardrail_budget_exhausted"
    assert prov.calls == 0                                       # FR-340: L1 also stopped
    # guardrail was denied -> never settled (nothing was reserved to refund)
    assert not any(p == "guardrail" for p, _, _ in settles)


async def test_guardrail_reserve_is_two_calls_worth(patched):
    reserves, _, _ = patched
    await _classify(_Prov(), _Guard())
    g_reserve = next(est for p, est in reserves if p == "guardrail")
    # reserve == 2 * estimate(gpt-4o-mini, 8000 in, 256 out): pricing 0.15/0.60 per 1M
    expected = 2 * ((8000 / 1_000_000) * 0.15 + (256 / 1_000_000) * 0.60)
    assert abs(g_reserve - expected) < 1e-9


async def test_l1_reserve_refunded_if_guardrail_reserve_errors(monkeypatch):
    # hardening: a DB error in the guardrail reserve (AFTER L1 reserved) must NOT leak the L1
    # reservation — the finally block refunds it (settle 0). The error still propagates.
    settles = []

    async def fake_reserve(conn, provider, ps, pe, est, budget):
        if provider == "guardrail":
            raise RuntimeError("db blip during guardrail reserve")
        return True                                   # L1 reserved + committed

    async def fake_settle(conn, provider, ps, est, model, tin, tout, pricing=None):
        settles.append((provider, tin, tout))
        return 0.0

    async def fake_persist(conn, *, device_id, outcome, applied_ids):
        return None

    monkeypatch.setattr(dp, "budget_reserve", fake_reserve)
    monkeypatch.setattr(dp, "budget_settle", fake_settle)
    monkeypatch.setattr(dp, "persist_outcome", fake_persist)

    with pytest.raises(RuntimeError):
        await _classify(_Prov(), _Guard())
    assert ("openai", 0, 0) in settles                # L1 reserve was refunded, not leaked
    assert not any(p == "guardrail" for p, _, _ in settles)  # guardrail never committed -> no refund
