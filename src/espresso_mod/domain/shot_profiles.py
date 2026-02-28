from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ShotStep:
    seconds: float
    valve_open: float  # 0..1
    setpoint_c: float | None = None  # allow changing temperature mid-shot later

SHOT_PROFILES: dict[str, list[ShotStep]] = {
    "classic_espresso": [
        ShotStep(seconds=3.0, valve_open=0.2),   # gentle preinfusion
        ShotStep(seconds=25.0, valve_open=1.0),  # full flow
    ],
    "lungo": [
        ShotStep(seconds=3.0, valve_open=0.2),
        ShotStep(seconds=40.0, valve_open=1.0),
    ],
}
