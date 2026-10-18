from __future__ import annotations

import pytest

from espresso_mod.domain.pulse import Pulse
from espresso_mod.services.pacing import pulse_until, wait_until


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
