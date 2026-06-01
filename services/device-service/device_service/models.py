"""API request/response schemas (pydantic v2)."""
from __future__ import annotations

from datetime import datetime

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


class HealthOut(BaseModel):
    status: str
    pools: dict[str, str]