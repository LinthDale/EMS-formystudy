"""Contract drift gate: api/openapi.yml (1.x, single source of truth) vs the ACTUAL
device-service FastAPI routes (PRD-0005 §13.2 P1 task; api-contract-governance §5
"runtime drift test"; risk-register R-012 / PRD-0005 R2).

No Docker needed: the ASGI app is imported (never started). Run with:

    python -m pytest tests/contract -v

Meta-tests at the bottom prove the gate actually DETECTS drift: they run the same
comparison against a deliberately mutated COPY of the committed spec and assert
findings are raised. api/openapi.yml itself is never modified.
"""
from __future__ import annotations

import copy

import pytest

from .spec_compare import (
    compare_component_schemas,
    compare_paths,
    compare_query_params,
    diff_contract,
    normalize_schema,
)
from .spec_loader import device_service_subset, load_committed_spec, load_runtime_spec

GATE2_LIST_DEVICES_PARAMS = {"status", "stale", "type", "limit", "offset", "sort", "order"}
SORT_ALLOWLIST = {"device_id", "device_type", "status", "ai_confidence",
                  "created_at", "updated_at", "last_seen_at"}


@pytest.fixture(scope="module")
def committed_spec() -> dict:
    return load_committed_spec()


@pytest.fixture(scope="module")
def committed_subset(committed_spec) -> dict:
    return device_service_subset(committed_spec)


@pytest.fixture(scope="module")
def runtime_spec() -> dict:
    return load_runtime_spec()


# ── the gate ──────────────────────────────────────────────────────────────────

def test_committed_spec_vs_runtime_app_has_no_drift(committed_spec, committed_subset, runtime_spec):
    """THE drift gate: any mismatch in paths / methods / query params / success
    responses / request bodies / schema fields fails CI with a per-item report."""
    findings = diff_contract(committed_spec, runtime_spec, committed_subset)
    assert findings == [], (
        "api/openapi.yml has drifted from the device-service runtime "
        f"({len(findings)} finding(s)) — fix the spec or the code, bump info.version "
        "and add an api/CHANGELOG.md entry (api-contract-governance §2/§6):\n  - "
        + "\n  - ".join(findings)
    )


def test_committed_subset_covers_all_runtime_routes(committed_subset, runtime_spec):
    """Tag-based subset extraction must not silently shrink: every runtime route
    must be matched by a 'Device Service'-tagged path in the committed spec."""
    findings = compare_paths(committed_subset, runtime_spec.get("paths", {}))
    assert findings == [], "path drift:\n  - " + "\n  - ".join(findings)
    assert len(committed_subset) > 0, "no 'Device Service'-tagged paths found in openapi.yml"


def test_gate2_list_devices_params_exist_in_spec_and_runtime(committed_spec, committed_subset, runtime_spec):
    """PRD-0005 GATE-2 contract (openapi 1.3.0): GET /devices accepts
    type/limit/offset/sort/order (+ pre-existing status/stale) on BOTH sides,
    and the sort allowlist matches exactly."""
    from .spec_compare import query_params

    spec_item = committed_subset.get("/devices")
    run_item = runtime_spec["paths"].get("/devices")
    assert spec_item is not None, "GET /devices missing from openapi.yml Device Service subset"
    assert run_item is not None, "GET /devices missing from runtime app"

    spec_params = query_params(committed_spec, spec_item, spec_item["get"])
    run_params = query_params(runtime_spec, run_item, run_item["get"])
    for side, params in (("openapi.yml", spec_params), ("runtime", run_params)):
        missing = GATE2_LIST_DEVICES_PARAMS - set(params)
        assert missing == set(), f"GET /devices on {side} is missing query params: {sorted(missing)}"

    for side, params in (("openapi.yml", spec_params), ("runtime", run_params)):
        sort_enum = set(params["sort"]["schema"].get("enum", []))
        assert sort_enum == SORT_ALLOWLIST, (
            f"GET /devices sort allowlist on {side} is {sorted(sort_enum)}, "
            f"expected {sorted(SORT_ALLOWLIST)}")
        limit_schema = params["limit"]["schema"]
        assert (limit_schema.get("minimum"), limit_schema.get("maximum")) == (1, 500), (
            f"GET /devices limit bounds on {side} are "
            f"{limit_schema.get('minimum')}..{limit_schema.get('maximum')}, expected 1..500")


def test_deviceout_exposes_ai_confidence_and_confirmed_at_on_both_sides(committed_spec, runtime_spec):
    """The 1.3.0 additions PRD-0005 FR-510 depends on must exist in the spec AND
    the runtime model (DeviceOut.ai_confidence, DeviceOut.confirmed_at)."""
    for side, spec in (("openapi.yml", committed_spec), ("runtime", runtime_spec)):
        props = spec["components"]["schemas"]["DeviceOut"].get("properties", {})
        for field in ("ai_confidence", "confirmed_at"):
            assert field in props, f"DeviceOut.{field} missing on {side}"
    spec_conf = normalize_schema(
        committed_spec, committed_spec["components"]["schemas"]["DeviceOut"]["properties"]["ai_confidence"])
    assert (spec_conf.get("minimum"), spec_conf.get("maximum")) == (0, 1), (
        f"openapi.yml DeviceOut.ai_confidence bounds are "
        f"{spec_conf.get('minimum')}..{spec_conf.get('maximum')}, expected 0..1")


def test_committed_spec_version_is_semver(committed_spec):
    """api-contract-governance §2: info.version must be MAJOR.MINOR.PATCH."""
    version = str(committed_spec["info"]["version"])
    parts = version.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"openapi.yml info.version '{version}' is not semver MAJOR.MINOR.PATCH")


# ── meta-tests: prove the gate detects deliberate drift (on a COPY, never the real spec) ──

def _drifted(committed_spec: dict) -> dict:
    return copy.deepcopy(committed_spec)


def test_removed_response_field_in_spec_copy_is_detected_as_drift(committed_spec, runtime_spec):
    drifted = _drifted(committed_spec)
    del drifted["components"]["schemas"]["DeviceOut"]["properties"]["ai_confidence"]
    findings = compare_component_schemas(drifted, runtime_spec, {"DeviceOut"})
    assert any("ai_confidence" in f for f in findings), (
        f"gate failed to detect a removed DeviceOut.ai_confidence field: {findings}")


def test_removed_query_param_in_spec_copy_is_detected_as_drift(committed_spec, runtime_spec):
    drifted = _drifted(committed_spec)
    params = drifted["paths"]["/devices"]["get"]["parameters"]
    drifted["paths"]["/devices"]["get"]["parameters"] = [p for p in params if p.get("name") != "limit"]
    findings = compare_query_params(
        drifted, device_service_subset(drifted), runtime_spec, runtime_spec["paths"])
    assert any("'limit'" in f for f in findings), (
        f"gate failed to detect the removed GET /devices 'limit' param: {findings}")


def test_removed_path_in_spec_copy_is_detected_as_undocumented_route(committed_spec, runtime_spec):
    drifted = _drifted(committed_spec)
    del drifted["paths"]["/devices/{device_id}/human-review"]
    findings = compare_paths(device_service_subset(drifted), runtime_spec["paths"])
    assert any("human-review" in f and "not documented" in f for f in findings), (
        f"gate failed to flag the runtime-only /human-review route: {findings}")


def test_shrunk_sort_enum_in_spec_copy_is_detected_as_drift(committed_spec, runtime_spec):
    drifted = _drifted(committed_spec)
    for param in drifted["paths"]["/devices"]["get"]["parameters"]:
        if param.get("name") == "sort":
            param["schema"]["enum"] = [v for v in param["schema"]["enum"] if v != "ai_confidence"]
    findings = compare_query_params(
        drifted, device_service_subset(drifted), runtime_spec, runtime_spec["paths"])
    assert any("'sort' enum mismatch" in f for f in findings), (
        f"gate failed to detect the shrunk sort allowlist: {findings}")


def test_full_diff_on_drifted_spec_copy_reports_multiple_findings(committed_spec, runtime_spec):
    """End-to-end RED proof: a spec copy with three injected drifts must fail diff_contract."""
    drifted = _drifted(committed_spec)
    del drifted["components"]["schemas"]["DeviceOut"]["properties"]["confirmed_at"]
    del drifted["paths"]["/devices"]["post"]
    drifted["paths"]["/devices"]["get"]["parameters"] = [
        p for p in drifted["paths"]["/devices"]["get"]["parameters"] if p.get("name") != "type"]
    findings = diff_contract(drifted, runtime_spec, device_service_subset(drifted))
    assert len(findings) >= 3, (
        f"expected >=3 findings for 3 injected drifts, got {len(findings)}: {findings}")
