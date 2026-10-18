from __future__ import annotations

import time

import pytest

from espresso_mod.hal.gpio import GpioHeater, GpioPump, GpioValve


class FakePin:
    """Records what a GPIO line was told to do."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.closed = False

    def on(self) -> None:
        self.events.append("on")

    def off(self) -> None:
        self.events.append("off")

    def close(self) -> None:
        self.closed = True

    @property
    def is_on(self) -> bool:
        return bool(self.events) and self.events[-1] == "on"


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.002)
    return predicate()


# ---- heater: window arithmetic (driven directly, no thread or real waiting) ----


def _heater(pin, fake_clock, **kwargs) -> GpioHeater:
    kwargs.setdefault("window_s", 1.0)
    kwargs.setdefault("command_timeout_s", 60.0)
    return GpioHeater(pin, clock=fake_clock, **kwargs)


def test_heater_starts_with_the_pin_low(fake_clock):
    pin = FakePin()

    heater = _heater(pin, fake_clock)
    try:
        assert not pin.is_on
        # de-energised as the very first thing, before the chopper can act
        assert pin.events[0] == "off"
    finally:
        heater.close()


def test_duty_cycle_holds_the_pin_on_for_its_fraction(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock)
    try:
        heater.set_power(0.25)

        # on for the first quarter of the window, then off for the rest
        assert heater._drive() == pytest.approx(0.25)
        assert pin.is_on

        fake_clock.sleep(0.25)
        assert heater._drive() == pytest.approx(0.75)
        assert not pin.is_on

        # the next window starts clean
        fake_clock.sleep(0.75)
        assert heater._drive() == pytest.approx(0.25)
        assert pin.is_on
    finally:
        heater.close()


def test_full_duty_never_switches_the_pin_off(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock)
    try:
        heater.set_power(1.0)

        for _ in range(3):
            assert heater._drive() == pytest.approx(1.0)
            assert pin.is_on
            fake_clock.sleep(1.0)
    finally:
        heater.close()


def test_zero_duty_leaves_the_pin_low(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock)
    try:
        heater.set_power(0.0)
        assert heater._drive() == pytest.approx(1.0)
        assert not pin.is_on
    finally:
        heater.close()


# ---- heater: safety ----


def test_power_is_clamped(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock)
    try:
        heater.set_power(5.0)
        assert heater.get_power() == 1.0

        heater.set_power(-2.0)
        assert heater.get_power() == 0.0
    finally:
        heater.close()


def test_stale_commands_drop_the_power_to_zero(fake_clock):
    """A control loop that stalls must not leave the element latched on."""
    pin = FakePin()
    heater = _heater(pin, fake_clock, window_s=1.0, command_timeout_s=1.0)
    try:
        heater.set_power(1.0)
        assert heater.get_power() == 1.0

        fake_clock.sleep(1.5)

        assert heater.get_power() == 0.0
        heater._drive()
        assert not pin.is_on
    finally:
        heater.close()


def test_fresh_command_after_a_stall_is_honoured(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock, window_s=1.0, command_timeout_s=1.0)
    try:
        heater.set_power(1.0)
        fake_clock.sleep(2.0)
        assert heater.get_power() == 0.0

        heater.set_power(1.0)
        assert heater.get_power() == 1.0
    finally:
        heater.close()


def test_close_drives_the_pin_low_and_releases_it(fake_clock):
    pin = FakePin()
    heater = _heater(pin, fake_clock)
    heater.set_power(1.0)
    heater._drive()
    assert pin.is_on

    heater.close()

    assert not pin.is_on
    assert pin.closed


@pytest.mark.parametrize("window_s", [0.0, -1.0])
def test_invalid_window_rejected(fake_clock, window_s):
    with pytest.raises(ValueError, match="window_s"):
        GpioHeater(FakePin(), clock=fake_clock, window_s=window_s)


@pytest.mark.parametrize("command_timeout_s", [0.0, -1.0])
def test_invalid_command_timeout_rejected(fake_clock, command_timeout_s):
    with pytest.raises(ValueError, match="command_timeout_s"):
        GpioHeater(FakePin(), clock=fake_clock, command_timeout_s=command_timeout_s)


def test_chopper_thread_drives_the_pin():
    """End to end on real time: the thread reaches both edges of the window."""
    pin = FakePin()
    heater = GpioHeater(pin, window_s=0.02, command_timeout_s=60.0)
    try:
        heater.set_power(0.5)

        assert _wait_until(lambda: pin.is_on)
        assert _wait_until(lambda: not pin.is_on)
    finally:
        heater.close()
    assert not pin.is_on


# ---- valve ----


def test_valve_starts_closed():
    pin = FakePin()

    GpioValve(pin)

    assert not pin.is_on


def test_valve_opens_on_a_full_demand():
    pin = FakePin()
    valve = GpioValve(pin)

    valve.set_open(1.0)

    assert pin.is_on
    assert valve.get_open() == 1.0


@pytest.mark.parametrize("demand", [0.0, 0.2, 0.49])
def test_valve_stays_closed_below_the_threshold(demand):
    """A solenoid cannot be throttled, so a fractional demand leaves it shut."""
    pin = FakePin()
    valve = GpioValve(pin)

    valve.set_open(demand)

    assert not pin.is_on
    assert valve.get_open() == 0.0


def test_valve_closes_again():
    pin = FakePin()
    valve = GpioValve(pin)

    valve.set_open(1.0)
    valve.set_open(0.0)

    assert not pin.is_on
    assert valve.get_open() == 0.0


def test_valve_close_releases_the_pin():
    pin = FakePin()
    valve = GpioValve(pin)
    valve.set_open(1.0)

    valve.close()

    assert not pin.is_on
    assert pin.closed


# ---- pump ----


def test_pump_starts_off():
    pin = FakePin()

    pump = GpioPump(pin)

    assert not pin.is_on
    assert pump.get_on() is False


def test_pump_switches_on_and_off():
    pin = FakePin()
    pump = GpioPump(pin)

    pump.set_on(True)
    assert pin.is_on
    assert pump.get_on() is True

    pump.set_on(False)
    assert not pin.is_on
    assert pump.get_on() is False


def test_pump_close_drives_the_pin_low_and_releases_it():
    pin = FakePin()
    pump = GpioPump(pin)
    pump.set_on(True)

    pump.close()

    assert not pin.is_on
    assert pin.closed
