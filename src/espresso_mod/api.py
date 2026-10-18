from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from espresso_mod.config import settings
from espresso_mod.domain.drinks import DRINKS
from espresso_mod.domain.models import (
    ControlEnable,
    DrinkList,
    DrinkOut,
    HistoryResponse,
    KioskStatus,
    PourStatus,
    Setpoint,
    ShotStatus,
    State,
    TelemetryPoint,
    TelemetryResponse,
    ValveCmd,
)
from espresso_mod.domain.shot_profiles import SHOT_PROFILES
from espresso_mod.hal.base import PressureReading
from espresso_mod.services.runtime import Runtime

router = APIRouter()

_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def _pressure(rt: Runtime) -> PressureReading:
    """Read the brew-pressure sender, which is optional.

    A machine without one reports a fault instead of a plausible-looking zero.
    """
    if rt.pressure is None:
        return PressureReading(bar=0.0, ok=False, fault="No pressure sensor configured")
    return rt.pressure.read_pressure()


@router.get("/state", response_model=State)
def state() -> State:
    rt = get_runtime()
    reading = rt.sensor.read()
    pressure = _pressure(rt)
    return State(
        temp_c=reading.celsius,
        temp_ok=reading.ok,
        temp_fault=reading.fault,
        heater_power=rt.heater.get_power(),
        valve_open=rt.valve.get_open(),
        setpoint_c=rt.control.setpoint_c,
        control_enabled=rt.control.enabled,
        control_error=rt.control.last_error,
        pressure_bar=pressure.bar,
        pressure_ok=pressure.ok,
        pressure_fault=pressure.fault,
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
            pressure_bar=s.pressure_bar,
            pressure_ok=s.pressure_ok,
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
    if rt.doser.status().state == "pouring":
        raise HTTPException(409, "A drink is being poured")
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


# ---- Drinks & dosing ----


def _pour_status(rt: Runtime) -> PourStatus:
    st = rt.doser.status()
    return PourStatus(
        state=st.state,
        drink=st.drink,
        target_ml=st.target_ml,
        delivered_ml=st.delivered_ml,
        elapsed_s=st.elapsed_s,
        message=st.message,
    )


def _ready(rt: Runtime, target_c: float) -> bool:
    """True when the boiler is at ``target_c`` and the sensor is healthy."""
    reading = rt.sensor.read()
    return reading.ok and abs(reading.celsius - target_c) <= settings.ready_tolerance_c


def _kiosk_status(rt: Runtime) -> KioskStatus:
    reading = rt.sensor.read()
    setpoint_c = rt.control.setpoint_c
    pressure = _pressure(rt)
    return KioskStatus(
        temp_c=reading.celsius,
        temp_ok=reading.ok,
        temp_fault=reading.fault,
        setpoint_c=setpoint_c,
        control_enabled=rt.control.enabled,
        control_error=rt.control.last_error,
        ready=reading.ok and abs(reading.celsius - setpoint_c) <= settings.ready_tolerance_c,
        pressure_bar=pressure.bar,
        pressure_ok=pressure.ok,
        pressure_fault=pressure.fault,
        pour=_pour_status(rt),
    )


@router.get("/drinks", response_model=DrinkList)
def drinks() -> DrinkList:
    rt = get_runtime()
    return DrinkList(
        drinks=[
            DrinkOut(
                key=d.key,
                name=d.name,
                description=d.description,
                water_ml=d.water_ml,
                setpoint_c=d.setpoint_c,
            )
            for d in DRINKS.values()
        ],
        brew_flow_ml_s=rt.doser.brew_flow_ml_s,
    )


@router.get("/kiosk/status", response_model=KioskStatus)
def kiosk_status() -> KioskStatus:
    return _kiosk_status(get_runtime())


@router.post("/drinks/pour/{key}")
def drink_pour(key: str, force: bool = Query(False)) -> dict[str, Any]:
    rt = get_runtime()
    drink = DRINKS.get(key)
    if drink is None:
        raise HTTPException(404, f"Unknown drink '{key}'. Known: {list(DRINKS)}")

    if rt.shots.status().state == "running":
        raise HTTPException(409, "A shot is already running")

    # Adopt the drink's temperature and make sure the loop is running, so tapping
    # a drink starts heating even on a machine that has just booted.
    rt.control.set_enabled(True)
    rt.control.set_setpoint(drink.setpoint_c)

    if not force and not _ready(rt, drink.setpoint_c):
        raise HTTPException(
            409,
            f"Boiler is not at {drink.setpoint_c:.0f} °C yet. "
            "Pass force=true to pour anyway.",
        )

    try:
        rt.doser.start(drink)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True, "pouring": drink.key, "target_ml": drink.water_ml}


@router.post("/drinks/cancel")
def drink_cancel() -> dict[str, Any]:
    get_runtime().doser.cancel()
    return {"ok": True}


# ---- History ----


@router.get("/history", response_model=HistoryResponse)
def history(limit: int = Query(20, ge=1, le=200)) -> HistoryResponse:
    """Newest first. Empty until something has been poured."""
    return HistoryResponse(entries=get_runtime().history.recent(limit))