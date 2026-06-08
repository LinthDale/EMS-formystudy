"""Unit: prompt rendering (no raw payload, JSON, deterministic)."""
import json

from device_service.llm.prompt import DEVICE_TYPES, SYSTEM_PROMPT, render_sample
from device_service.llm.types import CorrectionContext
from device_service.sanitizer import sanitize


def test_system_prompt_lists_device_types():
    for t in DEVICE_TYPES:
        assert t in SYSTEM_PROMPT


def test_render_sample_is_valid_json_with_fields():
    s = sanitize("sim-001", "ems/devices/sim-001/measurements", "ilp",
                 [{"voltage": 220.0, "current": 1.1}])
    rendered = render_sample(s)
    data = json.loads(rendered)
    names = {f["field_name"] for f in data["fields"]}
    assert names == {"voltage", "current"} and data["device_id"] == "sim-001"


def test_render_sample_no_raw_string_value():
    s = sanitize("d", "t", "json", [{"note": "TOPSECRET", "v": 1.0}])
    assert "TOPSECRET" not in render_sample(s)


def test_render_sample_includes_corrections():
    c = CorrectionContext("wrong_classification", "pressure", "was mislabelled", "2026-01-01T00:00:00Z")
    s = sanitize("d", "t", "ilp", [{"pressure": 101.0}], corrections=[c])
    data = json.loads(render_sample(s))
    assert data["human_corrections"][0]["corrected_device_type"] == "pressure"


def test_render_sample_deterministic():
    s = sanitize("d", "t", "ilp", [{"a": 1.0, "b": 2.0}])
    assert render_sample(s) == render_sample(s)