from __future__ import annotations

from pydantic import BaseModel, Field


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
    # Set when the control loop caught an exception; it cuts the heat and keeps
    # running, so this is the only sign that something is wrong.
    control_error: str | None = None
    # None when no pressure sender is configured or it could not be read.
    pressure_bar: float | None = None
    pressure_ok: bool = False
    pressure_fault: str | None = None


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
    pressure_bar: float | None = None
    pressure_ok: bool = True

class TelemetryResponse(BaseModel):
    points: list[TelemetryPoint]

class ShotStatus(BaseModel):
    state: str  # "idle" | "running" | "done" | "canceled" | "error"
    profile: str | None = None
    step_index: int = 0
    step_elapsed_s: float = 0.0
    total_elapsed_s: float = 0.0
    message: str | None = None


# ---- Drinks & dosing ----

class DrinkOut(BaseModel):
    key: str
    name: str
    description: str
    water_ml: float
    setpoint_c: float

class DrinkList(BaseModel):
    drinks: list[DrinkOut]
    brew_flow_ml_s: float

class PourStatus(BaseModel):
    state: str  # "idle" | "pouring" | "done" | "canceled" | "error"
    drink: str | None = None
    target_ml: float = 0.0
    delivered_ml: float = 0.0
    elapsed_s: float = 0.0
    message: str | None = None

class KioskStatus(BaseModel):
    """Everything the kiosk screen needs, in one poll."""

    temp_c: float
    temp_ok: bool
    temp_fault: str | None
    setpoint_c: float
    control_enabled: bool
    control_error: str | None = None
    ready: bool
    pressure_bar: float | None = None
    pressure_ok: bool = False
    pressure_fault: str | None = None
    pour: PourStatus


# ---- History ----

class HistoryEntry(BaseModel):
    id: int
    finished_at: float
    kind: str  # "shot" | "drink"
    name: str  # profile or drink key
    state: str  # "done" | "canceled" | "error"
    target_ml: float | None = None
    delivered_ml: float | None = None
    elapsed_s: float
    message: str | None = None
    peak_bar: float | None = None

class HistoryResponse(BaseModel):
    entries: list[HistoryEntry]


# ---- Health ----


class HealthStatus(BaseModel):
    """Liveness and readiness for a supervisor (systemd, a watchdog, a monitor).

    ``ok`` is the single bit a supervisor should act on; the rest is for a human
    reading the response while something is wrong. Pressure is optional and never
    makes a machine unhealthy.
    """

    ok: bool
    mode: str  # "sim" | "rtd"
    uptime_s: float
    running: bool  # a shot or a pour is in progress
    temp_ok: bool
    temp_fault: str | None = None
    pressure_ok: bool
    pressure_fault: str | None = None
    control_alive: bool
    control_enabled: bool
    control_error: str | None = None