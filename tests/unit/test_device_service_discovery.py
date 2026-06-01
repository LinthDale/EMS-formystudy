"""Unit: AdmissionGate (deny rules #5/#6) + ILP/JSON field parsing."""
from device_service.discovery import AdmissionGate, _gateway_for, parse_fields


def test_dedupe_within_window_then_expires():
    g = AdmissionGate(dedupe_window=60.0)
    g.record_candidate("t", now=100.0)
    assert g.is_duplicate("t", now=130.0)       # within 60s
    assert not g.is_duplicate("t", now=170.0)   # past 60s
    assert not g.is_duplicate("other", now=130.0)


def test_rate_limit():
    g = AdmissionGate(rate_limit=3, rate_window=60.0)
    for i in range(3):
        assert g.allow_rate(now=1000.0)
        g.record_candidate(f"t{i}", now=1000.0)
    assert not g.allow_rate(now=1000.0)         # 4th within window blocked
    assert g.allow_rate(now=1061.0)             # window slid


def test_parse_fields_ilp():
    f = parse_fields(b"meas,device_id=x voltage=220,current=1.1,n=5i,on=t,s=\"hi\" 1700000000", "ilp")
    assert f["voltage"] == 220.0 and f["current"] == 1.1 and f["n"] == 5 and f["on"] is True and f["s"] == "hi"


def test_parse_fields_ilp_malformed():
    assert parse_fields(b"justmeasurement", "ilp") == {}


def test_parse_fields_json():
    assert parse_fields(b'{"temp": 25.0, "hum": 60}', "json") == {"temp": 25.0, "hum": 60}


def test_parse_fields_json_invalid_or_nondict():
    assert parse_fields(b"not json", "json") == {}
    assert parse_fields(b"[1,2,3]", "json") == {}


def test_gateway_for():
    assert _gateway_for("ems/devices/x/measurements") == "ems-gateway"
    assert _gateway_for("ems/factory/x/measurements") == "kc-gateway"
    assert _gateway_for("factory/sensor/x") == "kc-ingest"
    assert _gateway_for("other") is None

async def test_apply_outcome_skips_non_candidate_row():
    from device_service.repositories.device_repo import apply_outcome
    class _Conn:
        async def fetchrow(self, q, *a):
            return {"status": "confirmed", "classified_by": "ai"}
        async def execute(self, *a):
            raise AssertionError("must not write when row is no longer a candidate")
    assert await apply_outcome(_Conn(), "x", object()) is False

async def test_oversized_payload_rejected_before_touching_db():
    from device_service.discovery import AdmissionGate, process_message
    from device_service.topic_parser import MAX_PAYLOAD_BYTES

    class _NoDB:
        @property
        def ai_pool(self):
            raise AssertionError("db must not be touched for an oversized payload")
        def ai_tx(self, **kw):
            raise AssertionError("db must not be touched for an oversized payload")

    payload = b"x" * (MAX_PAYLOAD_BYTES + 1)
    status = await process_message(
        "ems/devices/d/measurements", payload,
        db=_NoDB(), classifier=None, gate=AdmissionGate(), settings=None, now=1.0)
    assert status == "reject:mqtt_oversized_payload_total"