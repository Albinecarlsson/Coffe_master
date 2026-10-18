from __future__ import annotations

import time

import pytest

from espresso_mod.config import settings
from espresso_mod.hal.base import TempReading
from espresso_mod.hal.gpio import GpioHeater, GpioValve
from espresso_mod.services import runtime as runtime_module


class FakeSensor:
    def read(self) -> TempReading:
        return TempReading(celsius=20.0, ok=True)


class FakePin:
    def __init__(self) -> None:
        self.is_on = False
        self.closed = False

    def on(self) -> None:
        self.is_on = True

    def off(self) -> None:
        self.is_on = False

    def close(self) -> None:
        self.closed = True


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.002)
    return predicate()


def test_rtd_mode_builds_the_real_hardware_stack(monkeypatch):
    """HARDWARE_MODE=rtd wires the RTD sensor and the GPIO actuators together."""
    pins: dict[int, FakePin] = {}

    def fake_open_pin(number: int, *, active_high: bool = True) -> FakePin:
        device = FakePin()
        pins[number] = device
        return device

    monkeypatch.setattr(settings, "hardware_mode", "rtd")
    monkeypatch.setattr(settings, "heater_window_s", 0.02)
    monkeypatch.setattr(runtime_module, "open_sensor", lambda **kwargs: FakeSensor())
    monkeypatch.setattr(runtime_module, "open_output_pin", fake_open_pin)

    runtime = runtime_module.Runtime()
    try:
        assert isinstance(runtime.sensor, FakeSensor)
        assert isinstance(runtime.heater, GpioHeater)
        assert isinstance(runtime.valve, GpioValve)

        # the pins came from configuration, and both start de-energised
        assert set(pins) == {settings.heater_gpio_pin, settings.valve_gpio_pin}
        assert not any(pin.is_on for pin in pins.values())

        # the control loop drives the real heater, which chops the relay
        runtime.control.set_enabled(True)
        assert _wait_until(lambda: pins[settings.heater_gpio_pin].is_on)
    finally:
        runtime.stop()

    # shutdown cuts the element and releases both pins
    assert not any(pin.is_on for pin in pins.values())
    assert all(pin.closed for pin in pins.values())


def test_unknown_hardware_mode_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "hardware_mode", "banana")

    with pytest.raises(ValueError, match="banana"):
        runtime_module.Runtime()
