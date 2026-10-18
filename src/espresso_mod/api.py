from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from espresso_mod.domain.models import (
    ControlEnable,
    Setpoint,
    ShotStatus,
    State,
    TelemetryPoint,
    TelemetryResponse,
    ValveCmd,
)
from espresso_mod.domain.shot_profiles import SHOT_PROFILES
from espresso_mod.services.runtime import Runtime

router = APIRouter()

_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


@router.get("/state", response_model=State)
def state() -> State:
    rt = get_runtime()
    reading = rt.sensor.read()
    return State(
        temp_c=reading.celsius,
        temp_ok=reading.ok,
        temp_fault=reading.fault,
        heater_power=rt.heater.get_power(),
        valve_open=rt.valve.get_open(),
        setpoint_c=rt.control.setpoint_c,
        control_enabled=rt.control.enabled,
    )


@router.get("/telemetry", response_model=TelemetryResponse)
def telemetry(seconds: float = Query(30.0, ge=0.1, le=3600.0)) -> TelemetryResponse:
    rt = get_runtime()
    samples = rt.telemetry.snapshot_last_seconds(seconds)
    points = [
        TelemetryPoint(
            ts=s.ts,
            temp_c=s.temp_c,
            temp_ok=s.temp_ok,
            heater_power=s.heater_power,
            valve_open=s.valve_open,
            setpoint_c=s.setpoint_c,
            control_enabled=s.control_enabled,
        )
        for s in samples
    ]
    return TelemetryResponse(points=points)


@router.post("/control/enable")
def control_enable(body: ControlEnable) -> dict[str, Any]:
    rt = get_runtime()
    rt.control.set_enabled(body.enabled)
    return {"ok": True, "enabled": rt.control.enabled}


@router.post("/control/setpoint")
def control_setpoint(body: Setpoint) -> dict[str, Any]:
    rt = get_runtime()
    rt.control.set_setpoint(body.setpoint_c)
    return {"ok": True, "setpoint_c": rt.control.setpoint_c}


@router.post("/valve")
def valve(body: ValveCmd) -> dict[str, Any]:
    rt = get_runtime()
    rt.valve.set_open(body.open_0_to_1)
    return {"ok": True, "valve_open": rt.valve.get_open()}


# ---- Non-blocking shot runner endpoints ----

@router.get("/shot/status", response_model=ShotStatus)
def shot_status() -> ShotStatus:
    st = get_runtime().shots.status()
    return ShotStatus(
        state=st.state,
        profile=st.profile,
        step_index=st.step_index,
        step_elapsed_s=st.step_elapsed_s,
        total_elapsed_s=st.total_elapsed_s,
        message=st.message,
    )


@router.post("/shot/start/{name}")
def shot_start(name: str) -> dict[str, Any]:
    rt = get_runtime()
    if name not in SHOT_PROFILES:
        raise HTTPException(404, f"Unknown profile '{name}'. Known: {list(SHOT_PROFILES.keys())}")
    try:
        rt.shots.start(name)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True, "started": name}


@router.post("/shot/cancel")
def shot_cancel() -> dict[str, Any]:
    rt = get_runtime()
    rt.shots.cancel()
    return {"ok": True}


@router.get("/shot/profiles")
def shot_profiles() -> dict[str, Any]:
    return {"profiles": list(SHOT_PROFILES.keys())}