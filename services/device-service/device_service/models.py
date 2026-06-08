"""API request/response schemas (pydantic v2)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"  # same shape as MQTT device_id (FR-322)


class DeviceCreate(BaseModel):
    device_id: str = Field(pattern=_ID_PATTERN)
    device_type: str | None = None
    protocol: str | None = None
    vendor: str | None = None
    model: str | None = None
    location: str | None = None
    gateway_id: str | None = None


class DeviceUpdate(BaseModel):
    device_type: str | None = None
    protocol: str | None = None
    vendor: str | None = None
    model: str | None = None
    location: str | None = None
    gateway_id: str | None = None


class DeviceOut(BaseModel):
    device_id: str
    device_type: str | None = None
    status: str
    protocol: str | None = None
    vendor: str | None = None
    model: str | None = None
    location: str | None = None
    gateway_id: str | None = None
    classified_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_seen_at: datetime | None = None
    confirmed_at: datetime | None = None


class SignalCreate(BaseModel):
    signal_name: str = Field(pattern=_ID_PATTERN)
    unit: str | None = None
    datatype: str | None = None
    direction: str | None = None
    source_ref: str | None = None


class SignalOut(BaseModel):
    id: int
    device_id: str
    signal_name: str
    unit: str | None = None
    datatype: str | None = None
    direction: str | None = None
    status: str


class OverrideRequest(BaseModel):
    device_type: str
    signals: list[SignalCreate] = []


class DigestOut(BaseModel):
    """Human-review digest envelope (PRD-0003 §8.4). `digest` is the fixed-shape JSON
    built by digest.py (llm or system_fallback); kept as a free dict to avoid drift."""
    device_id: str
    digest: dict
    summary_source: str
    generated_at: datetime | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None


class CorrectionCreate(BaseModel):
    verdict: Literal["wrong_classification", "wrong_signals", "wrong_unit", "missed_signal", "good_with_note"]
    corrected_device_type: str | None = None
    corrected_signals: list[SignalCreate] | None = None
    human_explanation: str
    # FR-330 action flags. Behaviour (immediate re-classify / unfreeze->candidate) lands in
    # slice 2c with the classify path; until then a true value is rejected (never silently
    # ignored). prompt_version_at_correction is server-stamped provenance, NOT a client field.
    rerun_classification: bool = False
    demote_to_candidate: bool = False


class CorrectionDeactivateRequest(BaseModel):
    reason: str  # PRD §624 body field name; validated like human_explanation (§7.3a)


class CorrectionOut(BaseModel):
    id: int
    device_id: str
    verdict: str
    corrected_device_type: str | None = None
    corrected_signals: list[dict] | None = None
    human_explanation: str
    created_at: datetime | None = None
    created_by_key_id: str
    salt_version: str
    prompt_version_at_correction: str | None = None
    applied_count: int
    last_applied_at: datetime | None = None
    is_active: bool
    deactivated_at: datetime | None = None
    deactivation_reason: str | None = None


class HealthOut(BaseModel):
    status: str
    pools: dict[str, str]
