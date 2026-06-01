"""Unit: sanitizer FR-328 — strip strings/PII, cap fields/samples, numeric stats only."""
from device_service.sanitizer import MAX_FIELDS, MAX_SAMPLES, sanitize


def test_numeric_field_summarised_min_max():
    s = sanitize("d", "t", "ilp", [{"voltage": 219.5}, {"voltage": 221.0}, {"voltage": 220.0}])
    f = next(f for f in s.fields if f.field_name == "voltage")
    assert f.datatype == "float" and f.value_min == 219.5 and f.value_max == 221.0
    assert f.sample_count == 3


def test_bool_field_records_true_ratio():
    s = sanitize("d", "t", "ilp", [{"pump_on": True}, {"pump_on": False}, {"pump_on": True}])
    f = next(f for f in s.fields if f.field_name == "pump_on")
    assert f.datatype == "bool" and abs(f.bool_true_ratio - 0.6667) < 1e-3


def test_string_value_is_stripped_only_distinct_count_kept():
    s = sanitize("d", "t", "json", [{"note": "hello"}, {"note": "world"}, {"note": "hello"}])
    f = next(f for f in s.fields if f.field_name == "note")
    assert f.datatype == "string" and f.distinct_count == 2
    assert "hello" not in repr(s) and "world" not in repr(s)


def test_pii_field_name_dropped_entirely():
    s = sanitize("d", "t", "json", [{"owner_name": "Dale", "voltage": 220.0}])
    names = {f.field_name for f in s.fields}
    assert "owner_name" not in names and "voltage" in names
    assert "Dale" not in repr(s)


def test_field_count_capped():
    row = {f"f{i}": i for i in range(MAX_FIELDS + 20)}
    s = sanitize("d", "t", "ilp", [row])
    assert len(s.fields) == MAX_FIELDS


def test_sample_count_capped():
    rows = [{"voltage": float(i)} for i in range(MAX_SAMPLES + 10)]
    s = sanitize("d", "t", "ilp", rows)
    assert s.sample_count == MAX_SAMPLES


def test_property_no_raw_string_value_leaks():
    rows = [{"label": "SECRET_PAYLOAD_XYZ", "current": 1.2} for _ in range(3)]
    s = sanitize("d", "t", "json", rows)
    assert "SECRET_PAYLOAD_XYZ" not in repr(s)

# --- regression tests from code review (RED first) ---

def test_pii_segment_match_keeps_core_fields():
    """HIGH-1: substring 'lat' must NOT drop cumulative_kwh / calculated_power / accumulated_kwh."""
    s = sanitize("d", "t", "ilp", [{"cumulative_kwh": 1.0, "calculated_power": 2.0, "accumulated_kwh": 3.0}])
    names = {f.field_name for f in s.fields}
    assert {"cumulative_kwh", "calculated_power", "accumulated_kwh"} <= names


def test_pii_real_fields_still_dropped():
    s = sanitize("d", "t", "json", [{"gps_lat": 25.0, "user_id": "u1", "owner": "x", "voltage": 220.0}])
    names = {f.field_name for f in s.fields}
    assert names == {"voltage"}


def test_nan_inf_never_in_min_max():
    """HIGH-3: NaN/Inf must not propagate into value_min/value_max."""
    import math
    s = sanitize("d", "t", "ilp", [{"v": float("nan")}, {"v": float("inf")}, {"v": 220.0}])
    f = next((f for f in s.fields if f.field_name == "v"), None)
    if f is not None and f.value_min is not None:
        assert math.isfinite(f.value_min) and math.isfinite(f.value_max)