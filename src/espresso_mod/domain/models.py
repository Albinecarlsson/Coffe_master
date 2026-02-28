from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
class ControlEnable(BaseModel):
    enabled: bool

class Setpoint(BaseModel):
    setpoint_c: float = Field(..., ge=0, le=130)

class ValveCmd(BaseModel):
    open_0_to_1: float = Field(..., ge=0.0, le=1.0)

class State(BaseModel):
    temp_c: float
    temp_ok: bool
    temp_fault: str | None
    heater_power: float
    valve_open: float
    setpoint_c: float
    control_enabled: bool


class TelemetryQuery(BaseModel):
    seconds: float = Field(30.0, ge=0.1, le=3600.0)

class TelemetryPoint(BaseModel):
    ts: float
    temp_c: float
    temp_ok: bool
    heater_power: float
    valve_open: float
    setpoint_c: float
    control_enabled: bool

class TelemetryResponse(BaseModel):
    points: List[TelemetryPoint]

class ShotStatus(BaseModel):
    state: str  # "idle" | "running" | "done" | "canceled" | "error"
    profile: Optional[str] = None
    step_index: int = 0
    step_elapsed_s: float = 0.0
    total_elapsed_s: float = 0.0
    message: Optional[str] = None