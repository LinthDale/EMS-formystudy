"""Deterministic MockProvider (ADR-009).

Used for tests, budget-exhausted fallback, and LLM-failure fallback. Same input
always yields the same output (no randomness, no clock).
"""
from __future__ import annotations

from .types import ClassificationResult, SanitizedSample, SignalSuggestion

_UNIT = {
    "voltage": "V", "current": "A", "power_kw": "kW", "energy_kwh": "kWh",
    "temperature": "degC", "humidity": "%RH", "motor_speed": "RPM",
    "pressure": "kPa",
}


def _unit_for(name: str) -> str:
    return _UNIT.get(name, "")


def _classify(field_names: set[str], topic: str) -> tuple[str, float]:
    elec = {"voltage", "current", "power_kw", "energy_kwh"}
    if field_names & elec or topic.startswith("ems/devices/"):
        return "electricity", 0.95
    if "pressure" in field_names and "temperature" not in field_names:
        return "pressure", 0.95
    if "motor_speed" in field_names and field_names <= {"motor_speed"}:
        return "motor", 0.95
    if "temperature" in field_names and field_names <= {"temperature", "humidity"}:
        return "temperature", 0.95
    if {"pump_on", "valve_open", "valve_state"} & field_names:
        return "valve", 0.6
    return "unknown", 0.4


class MockProvider:
    name = "mock"

    async def classify_device(
        self, device_id: str, topic: str, sanitized: SanitizedSample
    ) -> ClassificationResult:
        field_names = {f.field_name for f in sanitized.fields}
        device_type, confidence = _classify(field_names, topic)
        signals = tuple(
            SignalSuggestion(
                signal_name=f.field_name,
                unit=_unit_for(f.field_name),
                datatype="bool" if f.datatype == "bool" else "float",
                direction="read",
            )
            for f in sanitized.fields
        )
        reasoning = (
            f"deterministic mock: matched device_type={device_type} from "
            f"{len(field_names)} fields on topic prefix"
        )
        return ClassificationResult(
            device_type=device_type,
            suggested_signals=signals,
            confidence=confidence,
            reasoning=reasoning,
            raw_response={"provider": "mock"},
        )