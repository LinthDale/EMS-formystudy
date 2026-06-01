"""Unit: provider payload -> ClassificationResult coercion."""
from device_service.llm.parsing import result_from_dict


def test_full_payload():
    r = result_from_dict(
        {
            "device_type": "electricity",
            "confidence": 0.95,
            "reasoning": "looks electrical",
            "suggested_signals": [
                {"signal_name": "voltage", "unit": "V", "datatype": "float", "direction": "read"}
            ],
        },
        {"provider": "x"},
    )
    assert r.device_type == "electricity" and r.confidence == 0.95
    assert r.suggested_signals[0].signal_name == "voltage"
    assert r.raw_response["provider"] == "x"


def test_missing_fields_use_defaults():
    r = result_from_dict({}, {})
    assert r.device_type == "unknown" and r.confidence == 0.0 and r.suggested_signals == ()


def test_bad_confidence_coerced_to_zero():
    r = result_from_dict({"device_type": "x", "confidence": "not-a-number"}, {})
    assert r.confidence == 0.0


def test_signals_not_a_list_ignored():
    r = result_from_dict({"suggested_signals": "oops"}, {})
    assert r.suggested_signals == ()


def test_non_dict_signal_items_skipped():
    r = result_from_dict({"suggested_signals": ["bad", {"signal_name": "v"}]}, {})
    assert len(r.suggested_signals) == 1 and r.suggested_signals[0].signal_name == "v"