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

class HeaterActuator(Protocol):
    def set_power(self, power_0_to_1: float) -> None: ...
    def get_power(self) -> float: ...

class ValveActuator(Protocol):
    def set_open(self, open_0_to_1: float) -> None: ...
    def get_open(self) -> float: ...
