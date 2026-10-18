from __future__ import annotations

from dataclasses import dataclass

from espresso_mod.domain.pulse import Pulse


@dataclass(frozen=True)
class ShotStep:
    seconds: float
    # 0..1. The solenoid is binary, so any non-zero demand opens it fully.
    valve_open: float
    # False keeps the pump off while the valve stays open, so the pressure in the
    # puck can decay. That is a dwell, not a pour.
    pump_on: bool = True
    # Cycle the pump while this step runs: wet the puck, then let it soak. The
    # step's ``seconds`` is the bound, so the last cycle may be cut short.
    pulse: Pulse | None = None
    setpoint_c: float | None = None  # allow changing temperature mid-shot later


# A solenoid cannot be throttled and a vibration pump cannot be turned down, so
# "gentle" here means pulsing the pump: short bursts at full pressure separated by
# soaks, which is the one form of preinfusion this machine can actually do. The
# timings come from the pump's flow rate and the basket, so treat them as a
# starting point and tune on the bench (docs/renovation.md, Phase 4).
_PREINFUSION = Pulse(on_s=1.5, off_s=1.5)

SHOT_PROFILES: dict[str, list[ShotStep]] = {
    "classic_espresso": [
        ShotStep(seconds=6.0, valve_open=1.0, pulse=_PREINFUSION),
        ShotStep(seconds=25.0, valve_open=1.0),
    ],
    "lungo": [
        ShotStep(seconds=6.0, valve_open=1.0, pulse=_PREINFUSION),
        ShotStep(seconds=40.0, valve_open=1.0),
    ],
}
