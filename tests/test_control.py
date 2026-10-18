from __future__ import annotations

import time

from espresso_mod.hal.base import TempReading
from espresso_mod.services.control import ControlLoop


class FakeSensor:
    def __init__(self, celsius: float = 20.0, ok: bool = True, fault: str | None = None) -> None:
        self.celsius = celsius
        self.ok = ok
        self.fault = fault

    def read(self) -> TempReading:
        return TempReading(celsius=self.celsius, ok=self.ok, fault=self.fault)


class FakeHeater:
    def __init__(self) -> None:
        self.power = 0.0

    def set_power(self, power_0_to_1: float) -> None:
        self.power = power_0_to_1

    def get_power(self) -> float:
        return self.power


class FakeValve:
    def __init__(self) -> None:
        self.open = 0.0

    def set_open(self, open_0_to_1: float) -> None:
        self.open = open_0_to_1

    def get_open(self) -> float:
        return self.open


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_control_disabled_never_powers_heater():
    sensor, heater, valve = FakeSensor(celsius=20.0), FakeHeater(), FakeValve()
    loop = ControlLoop(sensor, heater, valve, hz=100)
    loop.start()
    try:
        time.sleep(0.05)
        assert heater.power == 0.0
    finally:
        loop.stop()


def test_control_enabled_drives_heater_then_stops():
    sensor, heater, valve = FakeSensor(celsius=20.0), FakeHeater(), FakeValve()
    loop = ControlLoop(sensor, heater, valve, hz=100)
    loop.start()
    try:
        loop.set_enabled(True)
        assert _wait_until(lambda: heater.power > 0.0)

        loop.set_enabled(False)
        assert _wait_until(lambda: heater.power == 0.0)
    finally:
        loop.stop()


def test_control_fault_immediately_zeros_heater_power():
    """Safe-by-default: an invalid sensor reading must cut heater power."""
    sensor, heater, valve = FakeSensor(celsius=20.0), FakeHeater(), FakeValve()
    loop = ControlLoop(sensor, heater, valve, hz=100)
    loop.start()
    try:
        loop.set_enabled(True)
        assert _wait_until(lambda: heater.power > 0.0)

        sensor.ok = False
        sensor.fault = "open circuit"

        assert _wait_until(lambda: heater.power == 0.0)
    finally:
        loop.stop()
