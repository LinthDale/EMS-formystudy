"""Shared BFF/agent wire contract; copied unchanged into wrapper images."""
from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, UUID4, model_validator

SimulatorId = Literal["sim-001", "plc-001", "sensor-001", "delta-sim-001"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MeterSettings(StrictModel):
    noise_voltage_v: float = Field(3, ge=0, le=20, strict=True)
    current_base_a: float = Field(100, ge=0, le=1000, strict=True)
    current_swing_a: float = Field(40, ge=0, le=1000, strict=True)
    noise_current_a: float = Field(2, ge=0, le=20, strict=True)
    power_factor: float = Field(.85, ge=0, le=1, strict=True)
    period_seconds: float = Field(3600, ge=1, le=86400, strict=True)
    fault_mode: Literal["none", "zero", "freeze"] = "none"


class PLCSettings(StrictModel):
    motor_speed: int = Field(0, ge=0, le=65535, strict=True)
    pump_on: bool = Field(False, strict=True)
    valve_open: bool = Field(False, strict=True)


class SensorSettings(StrictModel):
    enabled: bool = Field(True, strict=True)
    interval_seconds: Literal[1, 5, 10, 15, 30, 2] = 2

    @model_validator(mode="before")
    @classmethod
    def strict_interval(cls, value):
        if isinstance(value, dict) and "interval_seconds" in value:
            if type(value["interval_seconds"]) is not int:
                raise ValueError("interval_seconds must be integer seconds")
        return value


class DeltaSettings(StrictModel):
    scenario: Literal["day", "night", "alarm"] = "day"


MODELS = {"sim-001": MeterSettings, "plc-001": PLCSettings,
          "sensor-001": SensorSettings, "delta-sim-001": DeltaSettings}


def validate_changes(simulator_id: str, changes: dict) -> dict:
    if simulator_id not in MODELS or not changes or len(changes) > 7:
        raise ValueError("unknown simulator or empty changes")
    return MODELS[simulator_id].model_validate(changes).model_dump(exclude_unset=True)


def validate_settings(simulator_id: str, settings: dict) -> dict:
    model = MODELS[simulator_id]
    if set(settings) != set(model.model_fields):
        raise ValueError("incomplete settings")
    return model.model_validate(settings).model_dump()


class Command(StrictModel):
    request_id: UUID4
    expected_instance_id: UUID4
    expected_revision: int = Field(ge=0, le=4096, strict=True)
    changes: dict = Field(min_length=1, max_length=7)
    reason: str = Field(min_length=1, max_length=200, pattern=r"\S")


class ApplyCommand(Command):
    deadline: float = Field(gt=0, strict=True)


class Snapshot(StrictModel):
    simulator_id: SimulatorId
    instance_id: UUID4
    revision: int = Field(ge=0, le=4096, strict=True)
    settings: dict

    @model_validator(mode="after")
    def settings_match(self):
        self.settings = validate_settings(self.simulator_id, self.settings)
        return self


class Receipt(StrictModel):
    request_id: UUID4
    command_hash: str = Field(pattern="^[a-f0-9]{64}$")
    changes: dict
    before: Snapshot
    after: Snapshot


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def command_hash(simulator_id: str, command: Command) -> str:
    fields = Command.model_validate(command.model_dump(exclude={"deadline"})).model_dump(mode="json")
    return hashlib.sha256(canonical({"simulator_id": simulator_id, **fields}).encode()).hexdigest()
