from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShotStep:
    seconds: float
    # 0..1. The solenoid is binary, so any non-zero demand opens it fully.
    valve_open: float
    setpoint_c: float | None = None  # allow changing temperature mid-shot later


# Multi-step profiles are supported, but a solenoid cannot be throttled and a
# vibration pump cannot be turned down, so every step today is the same full-flow
# pour. Real preinfusion needs pump pulsing (see docs/renovation.md), which needs
# the shot runner to drive the pump; until then a "gentle" step would be a lie.
SHOT_PROFILES: dict[str, list[ShotStep]] = {
    "classic_espresso": [
        ShotStep(seconds=28.0, valve_open=1.0),
    ],
    "lungo": [
        ShotStep(seconds=43.0, valve_open=1.0),
    ],
}
