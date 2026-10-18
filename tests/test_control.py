from __future__ import annotations

import time

from espresso_mod.hal.base import TempReading
from espresso_mod.services.control import ControlLoop


class FakeSensor:
    def __init__(
        self,
        celsius: float = 20.0,
        ok: bool = True,
        fault: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.celsius = celsius
        self.ok = ok
        self.fault = fault
        self.error = error

    def read(self) -> TempReading:
        if self.error is not None:
            raise self.error
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


# ---- loop faults ----


class ExplodingHeater(FakeHeater):
    def set_power(self, power_0_to_1: float) -> None:
        raise OSError("relay line gone")


def test_a_sensor_exception_cuts_the_heat_and_is_recorded():
    sensor, heater = FakeSensor(celsius=20.0), FakeHeater()
    loop = ControlLoop(sensor, heater, FakeValve(), hz=100)
    loop.set_enabled(True)
    loop._tick(0.1)
    assert heater.power > 0.0

    sensor.error = OSError("spi gone")
    loop._tick(0.1)

    assert heater.power == 0.0
    assert loop.last_error == "OSError: spi gone"
    assert loop.error_count == 1


def test_a_good_tick_clears_the_recorded_error():
    sensor = FakeSensor()
    loop = ControlLoop(sensor, FakeHeater(), FakeValve(), hz=100)
    sensor.error = RuntimeError("nope")
    loop._tick(0.1)
    assert loop.last_error == "RuntimeError: nope"

    sensor.error = None
    loop._tick(0.1)

    assert loop.last_error is None
    # the count survives, so repeated faults stay visible in diagnostics
    assert loop.error_count == 1


def test_an_actuator_exception_never_escapes_the_tick():
    loop = ControlLoop(FakeSensor(), ExplodingHeater(), FakeValve(), hz=100)
    loop.set_enabled(True)

    loop._tick(0.1)  # must not raise

    assert "OSError" in (loop.last_error or "")


def test_start_is_idempotent():
    loop = ControlLoop(FakeSensor(), FakeHeater(), FakeValve(), hz=100)
    loop.start()
    try:
        thread = loop._thread
        loop.start()  # a second start must not spawn a second loop
        assert loop._thread is thread
    finally:
        loop.stop()


def test_the_loop_keeps_controlling_after_a_fault():
    """A transient sensor fault must not need a restart."""
    sensor, heater = FakeSensor(celsius=20.0), FakeHeater()
    loop = ControlLoop(sensor, heater, FakeValve(), hz=100)
    loop.start()
    try:
        loop.set_enabled(True)
        assert _wait_until(lambda: heater.power > 0.0)

        sensor.error = OSError("blip")
        assert _wait_until(lambda: heater.power == 0.0)
        assert loop.last_error is not None

        sensor.error = None
        assert _wait_until(lambda: loop.last_error is None)
        assert _wait_until(lambda: heater.power > 0.0)
    finally:
        loop.stop()
