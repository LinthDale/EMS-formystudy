"""Unit: MQTT topic parser — Parser Matrix v3 + deny rules (PRD §8.5, ADR-013)."""
from device_service.topic_parser import (
    MAX_FIELDS, MAX_PAYLOAD_BYTES, parse,
)


# ---- Matrix rules #1-#3 (ems/<domain>/<id>/measurements) ----

def test_rule1_ems_devices_electricity():
    r = parse("ems/devices/meter-009/measurements")
    assert r.ok and r.matched_rule == 1
    assert r.device_id == "meter-009" and r.device_type == "electricity" and r.payload_format == "ilp"


def test_rule2_ems_factory_unknown():
    r = parse("ems/factory/plc-009/measurements")
    assert r.ok and r.matched_rule == 2 and r.device_type == "unknown"


def test_rule3_other_domain_unknown():
    r = parse("ems/solar/inv-009/measurements")
    assert r.ok and r.matched_rule == 3 and r.device_type == "unknown" and r.device_id == "inv-009"


# ---- Matrix rule #4 (factory/sensor/<sensor_id>) ----

def test_rule4_legacy_temp_01_maps_to_sensor_001():
    r = parse("factory/sensor/temp_01", payload={"temp": 25.0})
    assert r.ok and r.matched_rule == 4 and r.device_id == "sensor-001"


def test_rule4a_payload_device_id_wins():
    r = parse("factory/sensor/temp_99", payload={"device_id": "custom-77", "temp": 25.0})
    assert r.ok and r.device_id == "custom-77"


def test_rule4b_normalize_sensor_id():
    r = parse("factory/sensor/temp_02", payload={"temp": 25.0})
    assert r.ok and r.device_id == "sensor-temp-02" and r.device_type == "unknown" and r.payload_format == "json"


def test_rule4a_invalid_payload_device_id_falls_back_to_normalize():
    r = parse("factory/sensor/temp_03", payload={"device_id": "bad id!", "temp": 1.0})
    assert r.ok and r.device_id == "sensor-temp-03"


def test_rule4b_invalid_sensor_id_rejected():
    r = parse("factory/sensor/has space", payload={"temp": 1.0})
    assert not r.ok and r.metric == "mqtt_invalid_id_total"


# ---- deny rule #1: unmatched topic ----

def test_unmatched_topic_rejected():
    for topic in ("random/topic/foo", "ems/devices/x", "factory/#", "ems/x/y/z/measurements", "factory/sensor/a/b"):
        r = parse(topic)
        assert not r.ok and r.metric == "unmatched_topic_total", topic


def test_factory_non_sensor_rejected():
    r = parse("factory/plc/foo")
    assert not r.ok and r.metric == "unmatched_topic_total"


# ---- deny rule #2: id regex ----

def test_invalid_device_id_in_ems_topic_rejected():
    r = parse("ems/devices/" + "x" * 65 + "/measurements")
    assert not r.ok and r.metric == "mqtt_invalid_id_total"


# ---- deny rule #3: payload size ----

def test_oversized_payload_rejected():
    r = parse("ems/devices/m1/measurements", payload={"v": 1}, payload_size=MAX_PAYLOAD_BYTES + 1)
    assert not r.ok and r.metric == "mqtt_oversized_payload_total"


def test_payload_size_at_limit_ok():
    r = parse("ems/devices/m1/measurements", payload={"v": 1}, payload_size=MAX_PAYLOAD_BYTES)
    assert r.ok


# ---- deny rule #4: field count ----

def test_oversized_fields_rejected():
    big = {f"f{i}": i for i in range(MAX_FIELDS + 1)}
    r = parse("ems/devices/m1/measurements", payload=big)
    assert not r.ok and r.metric == "mqtt_oversized_fields_total"


def test_field_count_at_limit_ok():
    ok_payload = {f"f{i}": i for i in range(MAX_FIELDS)}
    r = parse("ems/devices/m1/measurements", payload=ok_payload)
    assert r.ok