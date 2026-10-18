from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TempReading:
    celsius: float
    ok: bool = True
    fault: str | None = None

class TemperatureSensor(Protocol):
    def read(self) -> TempReading: ...

@dataclass(frozen=True)
class PressureReading:
    bar: float
    ok: bool = True
    fault: str | None = None

class PressureSensor(Protocol):
    # Named rather than `read` because the simulated plant implements both this
    # and TemperatureSensor, and the two readings are not interchangeable.
    def read_pressure(self) -> PressureReading: ...

class HeaterActuator(Protocol):
    def set_power(self, power_0_to_1: float) -> None: ...
    def get_power(self) -> float: ...

class ValveActuator(Protocol):
    def set_open(self, open_0_to_1: float) -> None: ...
    def get_open(self) -> float: ...

class PumpActuator(Protocol):
    def set_on(self, on: bool) -> None: ...
    def get_on(self) -> bool: ...

class Closable(Protocol):
    """A hardware resource holding an OS handle that must be released on shutdown."""

    def close(self) -> None: ...
