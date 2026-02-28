"""
Hardware stub for MAX31865 + RTD.

Implement later using a library (e.g., spidev + MAX31865 driver).
Keep this module import-safe on non-Pi machines (no GPIO imports at module top).
"""
from __future__ import annotations
from espresso_mod.hal.base import TempReading, TemperatureSensor

class Max31865RtdSensor(TemperatureSensor):
    def __init__(self, spi_bus: int = 0, spi_dev: int = 0) -> None:
        self._spi_bus = spi_bus
        self._spi_dev = spi_dev

    def read(self) -> TempReading:
        # Placeholder behavior for dev; replace with real read.
        return TempReading(celsius=25.0, ok=False, fault="MAX31865 not implemented")
