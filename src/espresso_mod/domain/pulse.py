"""Pump on/off cycling.

Shared by shot steps and drink pours: wet the puck at low average pressure, let
the pressure decay into it, then extract. The right timings depend on the pump,
the basket and the grind, so these are starting points to tune on the bench.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pulse:
    """A pump on/off cycle, repeated for as long as the caller allows."""

    on_s: float
    off_s: float

    def __post_init__(self) -> None:
        if self.on_s <= 0.0:
            raise ValueError(f"Pulse.on_s must be positive, got {self.on_s}")
        if self.off_s < 0.0:
            raise ValueError(f"Pulse.off_s must be >= 0, got {self.off_s}")
