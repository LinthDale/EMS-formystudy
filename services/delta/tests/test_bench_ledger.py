"""Acceptance accounting must expose missing slots and duplicate DB rows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bench_ledger import reconcile, summarize_slots, validate_outages, summarize_outages, golden_errors, verification_bounds
import pytest


def test_missing_slot_and_read_failure_are_not_counted_as_success():
    events = [
        dict(kind="attempt", slot=0), dict(kind="read_ok", slot=0, duration=.2),
        dict(kind="committed", slot=0), dict(kind="attempt", slot=2),
        dict(kind="read_error", slot=2),
    ]
    result = summarize_slots(events, 3, 5)
    assert result["scheduled"] == 3, result
    assert result["attempted"] == 2, result
    assert result["valid"] == 1 and result["committed"] == 1, result
    assert result["missing_slots"] == [1], result
    assert not result["pass"], result


def test_same_slot_repeated_does_not_inflate_coverage():
    events = [dict(kind=k, slot=0, duration=.1) for k in
              ("attempt", "read_ok", "committed", "attempt", "read_ok", "committed")]
    result = summarize_slots(events, 2, 1)
    assert result["valid"] == 1, result
    assert result["duplicate_attempt_slots"] == [0], result
    assert not result["pass"], result


def test_exactly_one_valid_commit_per_slot_passes():
    events = [dict(kind=k, slot=i, duration=.2) for i in range(3)
              for k in ("attempt", "read_ok", "committed")]
    assert summarize_slots(events, 3, 1)["pass"], "complete run rejected"


def row(ns=1000, voltage=230):
    return dict(sampled_ns=ns, voltage=voltage, current=13, power_kw=9, energy_kwh=1234)


def test_equal_counts_with_missing_and_extra_time_fail():
    result = reconcile([row(1000), row(2000)], [row(1000), row(3000)])
    assert result["missing"] == [2000] and result["extra"] == [3000], result
    assert not result["pass"], result


def test_duplicate_and_changed_value_fail():
    result = reconcile([row()], [row(), row(voltage=231)])
    assert result["duplicates"] == [1000] and result["mismatched"] == [1000], result
    assert not result["pass"], result


def test_exact_values_pass_but_empty_or_nan_do_not():
    assert reconcile([row()], [row()])["pass"], "matching sample rejected"
    assert not reconcile([], [])["pass"], "empty run claimed success"
    assert not reconcile([row()], [row(voltage=float('nan'))])["pass"], "NaN accepted"


@pytest.mark.parametrize("outages", [[(10, 1)], [(1, 0)], [(1, 5), (3, 1)], [(1, -1)]])
def test_outside_or_overlapping_outages_rejected(outages):
    with pytest.raises(ValueError):
        validate_outages(outages, 10)


def test_valid_outages_allow_recovery_before_window_end():
    assert validate_outages([(1, 2), (5, 2)], 10) == [(1, 2), (5, 2)], "valid schedule rejected"


def test_duplicate_commit_cannot_be_hidden_by_set():
    events = [dict(kind=k, slot=0, duration=.1) for k in
              ("attempt", "read_ok", "committed", "committed")]
    assert not summarize_slots(events, 1, 1)["pass"], "duplicate commit accepted"


def test_restarted_without_successful_read_is_not_recovered():
    events = [dict(kind="outage_started", index=0, monotonic=10),
              dict(kind="outage_restarted", index=0, monotonic=40)]
    assert not summarize_outages(events, 1, 15)["pass"], "unverified restart accepted"


def test_outage_requires_error_and_bounded_recovery():
    events = [dict(kind="outage_started", index=0, monotonic=10),
              dict(kind="read_error", monotonic=15),
              dict(kind="outage_restarted", index=0, monotonic=40),
              dict(kind="read_ok", monotonic=46, started=45)]
    assert summarize_outages(events, 1, 15)["pass"], "recovery rejected"
    assert not summarize_outages(events, 1, 5)["pass"], "late recovery accepted"


def test_read_completed_after_restart_is_not_a_value_during_outage():
    events = [dict(kind="outage_started", index=0, monotonic=10),
              dict(kind="read_error", monotonic=15),
              dict(kind="outage_restarted", index=0, monotonic=40),
              dict(kind="read_ok", started=39, monotonic=41),
              dict(kind="read_ok", started=45, monotonic=45.3)]
    assert summarize_outages(events, 1, 15)["pass"], "real response after device restart counted as fake"


def test_night_zero_is_valid_but_wrong_state_or_scale_is_not():
    sample = dict(voltage=230, current=0, power_kw=0, energy_kwh=1234.56,
                  state=0, temperature_c=35, phases=[dict(voltage=230, frequency_hz=60)] * 3)
    assert golden_errors(sample, "night") == [], "known nighttime vector rejected"
    assert golden_errors({**sample, 'state': 2}, "night"), "wrong state accepted"
    assert golden_errors({**sample, 'voltage': 2300}, "night"), "wrong voltage scale accepted"


@pytest.mark.parametrize("energy", [12345.6, float('inf'), 1234.57])
def test_night_energy_must_match_independent_baseline(energy):
    sample = dict(voltage=230, current=0, power_kw=0, energy_kwh=energy,
                  state=0, temperature_c=35, phases=[dict(voltage=230, frequency_hz=60)] * 3)
    assert "energy" in golden_errors(sample, "night"), "invalid cumulative energy accepted"


def test_verification_covers_full_window_and_rejects_running_ledger():
    events = [dict(kind="window_start", utc="2026-11-12T00:00:00+00:00"),
              dict(kind="committed", sampled_ns=1794441601000000000),
              dict(kind="window_end", utc="2026-11-12T00:00:05+00:00")]
    assert verification_bounds(events) == (1794441600000000000, 1794441605000000000), "window narrowed to samples"
    with pytest.raises(ValueError):
        verification_bounds(events[:-1])
