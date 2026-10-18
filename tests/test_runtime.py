from __future__ import annotations

import time
from dataclasses import replace

import pytest

from espresso_mod.config import settings
from espresso_mod.domain.drinks import DRINKS
from espresso_mod.hal.base import PressureReading, TempReading
from espresso_mod.hal.gpio import GpioHeater, GpioPump, GpioValve
from espresso_mod.services import runtime as runtime_module
from espresso_mod.services.doser import PourState


class FakeSensor:
    def read(self) -> TempReading:
        return TempReading(celsius=20.0, ok=True)


class FakePressure:
    def __init__(self) -> None:
        self.closed = False

    def read_pressure(self) -> PressureReading:
        return PressureReading(bar=8.6, ok=True)

    def close(self) -> None:
        self.closed = True


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
    monkeypatch.setattr(runtime_module, "open_pressure_sensor", lambda **kwargs: FakePressure())

    runtime = runtime_module.Runtime()
    try:
        assert isinstance(runtime.sensor, FakeSensor)
        assert isinstance(runtime.heater, GpioHeater)
        assert isinstance(runtime.valve, GpioValve)
        assert isinstance(runtime.pump, GpioPump)
        assert isinstance(runtime.pressure, FakePressure)

        # the pins came from configuration, and all start de-energised
        assert set(pins) == {
            settings.heater_gpio_pin,
            settings.valve_gpio_pin,
            settings.pump_gpio_pin,
        }
        assert not any(pin.is_on for pin in pins.values())

        # the control loop drives the real heater, which chops the relay
        runtime.control.set_enabled(True)
        assert _wait_until(lambda: pins[settings.heater_gpio_pin].is_on)
    finally:
        runtime.stop()

    # shutdown cuts the element and releases every pin
    assert not any(pin.is_on for pin in pins.values())
    assert all(pin.closed for pin in pins.values())
    assert isinstance(runtime.pressure, FakePressure)
    assert runtime.pressure.closed


def test_rtd_mode_pours_through_the_pump_and_valve(monkeypatch):
    """A drink drives both real outputs, then leaves them both off."""
    pins: dict[int, FakePin] = {}

    def fake_open_pin(number: int, *, active_high: bool = True) -> FakePin:
        device = FakePin()
        pins[number] = device
        return device

    monkeypatch.setattr(settings, "hardware_mode", "rtd")
    monkeypatch.setattr(settings, "heater_window_s", 0.02)
    monkeypatch.setattr(settings, "brew_flow_ml_s", 300.0)
    # preinfusion is measured in real seconds; skip it so the test stays quick
    monkeypatch.setitem(
        DRINKS,
        "espresso",
        replace(DRINKS["espresso"], preinfusion=None, preinfusion_s=0.0),
    )
    monkeypatch.setattr(runtime_module, "open_sensor", lambda **kwargs: FakeSensor())
    monkeypatch.setattr(runtime_module, "open_output_pin", fake_open_pin)
    monkeypatch.setattr(runtime_module, "open_pressure_sensor", lambda **kwargs: FakePressure())

    runtime = runtime_module.Runtime()
    try:
        runtime.doser.start(DRINKS["espresso"])

        assert _wait_until(
            lambda: pins[settings.valve_gpio_pin].is_on and pins[settings.pump_gpio_pin].is_on
        )
        assert _wait_until(lambda: runtime.doser.status().state == "done")
    finally:
        runtime.stop()

    assert not pins[settings.valve_gpio_pin].is_on
    assert not pins[settings.pump_gpio_pin].is_on


def test_unknown_hardware_mode_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "hardware_mode", "banana")

    with pytest.raises(ValueError, match="banana"):
        runtime_module.Runtime()


def test_history_is_untouched_until_something_has_run():
    runtime = runtime_module.Runtime()
    try:
        # the callbacks only fire after a pour; before that there is nothing to log
        runtime._record_shot()
        runtime._record_pour()

        assert runtime.history.recent() == []
    finally:
        runtime.stop()


def test_a_finished_pour_is_logged_with_its_peak_pressure(fake_clock, monkeypatch):
    runtime = runtime_module.Runtime(clock=fake_clock)
    try:
        runtime.pressure_peak.observe(9.4)
        monkeypatch.setattr(
            runtime.doser,
            "status",
            lambda: PourState(
                state="done",
                drink="espresso",
                target_ml=30.0,
                delivered_ml=30.0,
                elapsed_s=27.0,
                message="Poured 30 ml",
            ),
        )

        runtime._record_pour()

        [entry] = runtime.history.recent()
        assert entry.name == "espresso"
        assert entry.peak_bar == pytest.approx(9.4)
    finally:
        runtime.stop()
