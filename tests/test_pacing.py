from __future__ import annotations

import math

import pytest

from espresso_mod.domain.pulse import Pulse
from espresso_mod.hal.base import PressureReading
from espresso_mod.services.pacing import pressure_cutoff, pulse_until, wait_until


class RecordingPump:
    def __init__(self) -> None:
        self.events: list[bool] = []
        self.on = False

    def set_on(self, on: bool) -> None:
        on = bool(on)
        if on != self.on:
            self.events.append(on)
        self.on = on

    def get_on(self) -> bool:
        return self.on


class StubPressure:
    def __init__(self, bar: float = 0.0, ok: bool = True, explode: bool = False) -> None:
        self._bar = bar
        self._ok = ok
        self._explode = explode

    def read_pressure(self) -> PressureReading:
        if self._explode:
            raise OSError("i2c bus gone")
        return PressureReading(bar=self._bar, ok=self._ok)


class PumpPressure:
    """Brew pressure that follows the pump, stepped by the (fake) clock.

    Nine bar while the pump runs, decaying to zero through the soak, so a burst
    really does cross the target instead of the predicate being scripted.
    """

    def __init__(self, pump: RecordingPump, clock, tau_s: float = 0.1) -> None:
        self._pump = pump
        self._clock = clock
        self._tau_s = tau_s
        self._bar = 0.0
        self._last = clock.now()

    def read_pressure(self) -> PressureReading:
        now = self._clock.now()
        dt = max(0.0, now - self._last)
        self._last = now
        target = 9.0 if self._pump.get_on() else 0.0
        self._bar += (target - self._bar) * (1.0 - math.exp(-dt / self._tau_s))
        return PressureReading(bar=self._bar, ok=True)


def test_wait_until_returns_when_the_deadline_passes(fake_clock):
    start = fake_clock.now()

    assert wait_until(fake_clock, start + 0.5, lambda: False) is True
    assert fake_clock.now() == pytest.approx(start + 0.5)


def test_wait_until_gives_up_when_cancelled(fake_clock):
    start = fake_clock.now()

    stopped = wait_until(fake_clock, start + 10.0, lambda: fake_clock.now() >= start + 0.1)

    assert stopped is False
    # it did not sit out the full deadline
    assert fake_clock.now() < start + 10.0


def test_pulse_until_cycles_the_pump(fake_clock):
    pump = RecordingPump()
    start = fake_clock.now()

    assert pulse_until(pump, fake_clock, Pulse(1.0, 0.5), start + 3.0, lambda: False) is True

    assert pump.events == [True, False, True, False]
    assert not pump.on


def test_pulse_until_switches_the_pump_off_when_cancelled_in_the_soak(fake_clock):
    pump = RecordingPump()
    start = fake_clock.now()

    completed = pulse_until(
        pump,
        fake_clock,
        Pulse(on_s=1.0, off_s=2.0),
        start + 10.0,
        lambda: fake_clock.now() >= start + 2.0,
    )

    assert completed is False
    assert not pump.on


# ---- pressure-guided bursts ----


def test_pressure_cutoff_is_disabled_without_a_sender_or_target():
    assert pressure_cutoff(None, 2.0) is None
    assert pressure_cutoff(StubPressure(9.0), 0.0) is None


def test_pressure_cutoff_rejects_a_negative_target():
    with pytest.raises(ValueError):
        pressure_cutoff(StubPressure(0.0), -1.0)


def test_pressure_cutoff_fires_at_or_above_the_target():
    at_target = pressure_cutoff(StubPressure(2.0), 2.0)
    below = pressure_cutoff(StubPressure(1.99), 2.0)

    assert at_target is not None and at_target() is True
    assert below is not None and below() is False


def test_pressure_cutoff_never_treats_a_fault_as_a_target():
    # 9 bar is well above the target, but the sender says it is not believable.
    faulty = pressure_cutoff(StubPressure(9.0, ok=False), 2.0)
    exploding = pressure_cutoff(StubPressure(explode=True), 2.0)

    assert faulty is not None and faulty() is False
    assert exploding is not None and exploding() is False


def test_pulse_until_cuts_each_burst_at_the_target_and_keeps_the_deadline(fake_clock):
    pump = RecordingPump()
    cut_when = pressure_cutoff(PumpPressure(pump, fake_clock), 2.0)
    start = fake_clock.now()

    completed = pulse_until(
        pump, fake_clock, Pulse(on_s=1.0, off_s=0.5), start + 3.0, lambda: False, cut_when=cut_when
    )

    assert completed is True
    assert fake_clock.now() == pytest.approx(start + 3.0)
    assert not pump.on
    # The step still runs its full 3 s, but as a train of short bursts: an
    # uncut 1 s on / 0.5 s off would produce only two ons in this window.
    assert pump.events.count(True) >= 4
    assert pump.events.count(False) == pump.events.count(True)


def test_pulse_until_does_not_start_a_burst_that_is_already_at_target(fake_clock):
    pump = RecordingPump()
    cut_when = pressure_cutoff(StubPressure(9.0), 2.0)
    start = fake_clock.now()

    completed = pulse_until(
        pump, fake_clock, Pulse(on_s=1.0, off_s=0.5), start + 2.0, lambda: False, cut_when=cut_when
    )

    assert completed is True
    assert pump.events == []
    assert fake_clock.now() == pytest.approx(start + 2.0)


def test_pulse_until_advances_time_even_with_a_zero_soak_at_target(fake_clock):
    # off_s=0 means "hold pressure"; the loop must not spin on the same instant.
    pump = RecordingPump()
    cut_when = pressure_cutoff(StubPressure(9.0), 2.0)
    start = fake_clock.now()

    completed = pulse_until(
        pump, fake_clock, Pulse(on_s=1.0, off_s=0.0), start + 0.1, lambda: False, cut_when=cut_when
    )

    assert completed is True
    assert pump.events == []
    assert fake_clock.now() == pytest.approx(start + 0.1)


def test_pulse_until_still_cancels_while_held_at_target(fake_clock):
    start = fake_clock.now()
    cut_when = pressure_cutoff(StubPressure(9.0), 2.0)

    completed = pulse_until(
        RecordingPump(),
        fake_clock,
        Pulse(on_s=1.0, off_s=0.5),
        start + 10.0,
        lambda: fake_clock.now() >= start + 0.3,
        cut_when=cut_when,
    )

    assert completed is False
    # Cancellation is noticed on the next 20 ms tick, not at an exact instant.
    assert start + 0.3 <= fake_clock.now() < start + 0.4
