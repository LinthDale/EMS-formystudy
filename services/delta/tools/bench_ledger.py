"""Pure, independent acceptance accounting; not a production receipt protocol."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math

FIELDS = ("voltage", "current", "power_kw", "energy_kwh")


def golden_errors(sample, scenario, elapsed=86400):
    """Independent literal bounds for the documented noise-disabled demo vectors."""
    checks = {
        "voltage": sample.get("voltage") == 230,
        "state": sample.get("state") == {"day": 2, "night": 0, "alarm": 4}[scenario],
        "temperature": sample.get("temperature_c") == 35,
        "energy": (math.isfinite(sample.get("energy_kwh", -1)) and
                   1234.56 <= sample.get("energy_kwh", -1) <= 1234.56 + 9.6 * elapsed / 3600 + .01)
                  if scenario == "day" else sample.get("energy_kwh") == 1234.56,
        "phases": len(sample.get("phases", [])) == 3 and all(
            p.get("voltage") == 230 and p.get("frequency_hz") == 60 for p in sample.get("phases", [])),
        "power": 8.399 <= sample.get("power_kw", -1) <= 9.6 if scenario == "day"
                 else sample.get("power_kw") == 0,
        "current": 12.16 <= sample.get("current", -1) <= 13.92 if scenario == "day"
                   else sample.get("current") == 0,
    }
    return [name for name, okay in checks.items() if not okay]


def verification_bounds(events):
    """Cover the entire completed run, including its sender settling period."""
    starts = [e for e in events if e["kind"] == "window_start"]
    ends = [e for e in events if e["kind"] == "window_end"]
    samples = [e["sampled_ns"] for e in events if e["kind"] == "committed"]
    if len(starts) != 1 or len(ends) != 1 or not samples:
        raise ValueError("verification requires one completed, nonempty run")
    def ns(event):
        delta = datetime.fromisoformat(event["utc"]) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400000000 + delta.seconds * 1000000 + delta.microseconds) * 1000
    return min(ns(starts[0]), min(samples)), max(ns(ends[0]), max(samples))


def validate_outages(outages, window):
    previous_end = 0
    for item in outages:
        if len(item) != 2:
            raise ValueError("outage needs offset and duration")
        offset, duration = item
        if offset < previous_end or duration <= 0 or offset + duration >= window:
            raise ValueError("outage must be ordered, nonoverlapping and end before window")
        previous_end = offset + duration
    return outages


def summarize_outages(events, count, recovery_limit):
    outcomes = []
    for index in range(count):
        starts = [e for e in events if e["kind"] == "outage_started" and e["index"] == index]
        restarts = [e for e in events if e["kind"] == "outage_restarted" and e["index"] == index]
        if len(starts) != 1 or len(restarts) != 1:
            outcomes.append(dict(index=index, passed=False, reason="missing_event"))
            continue
        begin, end = starts[0]["monotonic"], restarts[0]["monotonic"]
        next_start = min([e["monotonic"] for e in events
                          if e["kind"] == "outage_started" and e["monotonic"] > end]
                         or [float("inf")])
        errors = [e for e in events if e["kind"] == "read_error" and begin <= e["monotonic"] < end]
        successes = [e for e in events if e["kind"] == "read_ok"
                     and end <= e["started"] < next_start]
        delay = min([e["monotonic"] - end for e in successes] or [float("inf")])
        false_values = [e for e in events if e["kind"] == "read_ok"
                        and begin <= e["started"] and e["monotonic"] < end]
        outcomes.append(dict(index=index, errors=len(errors),
                             recovery_seconds=delay if math.isfinite(delay) else None,
                             spanning_reads=sum(e["kind"] == "read_ok" and
                                 e.get("started", end) < end <= e["monotonic"] for e in events),
                             false_values=len(false_values),
                             passed=bool(errors and delay <= recovery_limit and not false_values)))
    return dict(outcomes=outcomes, **{"pass": bool(count and all(x["passed"] for x in outcomes))})


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {name: ordered[max(0, math.ceil(len(ordered) * p) - 1)]
            for name, p in (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1))}


def summarize_slots(events, count, interval):
    attempts = Counter(e["slot"] for e in events if e["kind"] == "attempt")
    good_counts = Counter(e["slot"] for e in events if e["kind"] == "read_ok")
    commit_counts = Counter(e["slot"] for e in events if e["kind"] == "committed")
    good, committed = set(good_counts), set(commit_counts)
    expected = set(range(count))
    durations = percentiles([e["duration"] for e in events if e["kind"] == "read_ok"])
    duplicates = sorted(k for k, n in attempts.items() if n > 1)
    result = dict(scheduled=count, attempted=len(expected & attempts.keys()),
                  valid=len(expected & good), committed=len(expected & committed),
                  missing_slots=sorted(expected - attempts.keys()),
                  failed_slots=sorted(expected - good),
                  duplicate_attempt_slots=duplicates,
                  duplicate_read_slots=sorted(k for k, n in good_counts.items() if n > 1),
                  duplicate_commit_slots=sorted(k for k, n in commit_counts.items() if n > 1),
                  outside_slots=sorted(attempts.keys() - expected), poll_seconds=durations)
    result["pass"] = bool(count and attempts.keys() == good == committed == expected
                          and not duplicates and not result["duplicate_read_slots"]
                          and not result["duplicate_commit_slots"]
                          and durations and durations["p99"] < interval)
    return result


def reconcile(expected, actual):
    """Compare sample membership AND content. Equal counts alone are insufficient."""
    source, received = defaultdict(list), defaultdict(list)
    for row in expected:
        source[row["sampled_ns"]].append(row)
    for row in actual:
        received[row["sampled_ns"]].append(row)
    bad = []
    for ns in source.keys() & received.keys():
        if any(not all(math.isclose(float(row[k]), float(source[ns][0][k]),
                                    rel_tol=0, abs_tol=1e-6) for k in FIELDS)
               for row in received[ns]):
            bad.append(ns)
    result = dict(expected=len(expected), received=len(actual),
                  missing=sorted(source.keys() - received.keys()),
                  extra=sorted(received.keys() - source.keys()),
                  duplicates=sorted(ns for ns, rows in received.items() if len(rows) > 1),
                  source_duplicates=sorted(ns for ns, rows in source.items() if len(rows) > 1),
                  mismatched=sorted(bad))
    result["pass"] = bool(expected and not any(result[k] for k in
                          ("missing", "extra", "duplicates", "source_duplicates", "mismatched")))
    return result
