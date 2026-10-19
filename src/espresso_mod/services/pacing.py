"""Driving the pump over time, in a way that can be stopped promptly.

Both the shot runner and the doser need "keep doing this until a deadline, or
until someone cancels" (or, during preinfusion, until the puck reaches a target
pressure). Putting it here keeps the 20 ms polling loop in one place instead of
duplicated across two services.
"""

from __future__ import annotations

from collections.abc import Callable

from espresso_mod.domain.clock import Clock
from espresso_mod.domain.pulse import Pulse
from espresso_mod.hal.base import PressureSensor, PumpActuator

# How often we come up for air to check for a cancel.
_TICK_S = 0.02


def pressure_cutoff(
    sensor: PressureSensor | None, target_bar: float
) -> Callable[[], bool] | None:
    """A predicate that ends a pump burst once brew pressure reaches ``target_bar``.

    Returns ``None`` when there is no sender or guidance is disabled (``0``), so
    callers can pass it straight to :func:`pulse_until` and a machine without the
    optional sender keeps its timed preinfusion.

    A faulty reading is never a target: a sender that is unplugged, warming up or
    reporting garbage must not cut a burst on a number it is not standing behind.
    """
    if target_bar < 0.0:
        raise ValueError(f"preinfusion target must be >= 0, got {target_bar}")
    if sensor is None or target_bar == 0.0:
        return None

    def reached() -> bool:
        try:
            reading = sensor.read_pressure()
        except Exception:  # noqa: BLE001
            return False
        return reading.ok and reading.bar >= target_bar

    return reached


def wait_until(clock: Clock, deadline: float, should_stop: Callable[[], bool]) -> bool:
    """Sleep until ``deadline``. False as soon as ``should_stop`` says so."""
    while clock.now() < deadline:
        if should_stop():
            return False
        clock.sleep(min(_TICK_S, deadline - clock.now()))
    return not should_stop()


def pulse_until(
    pump: PumpActuator | None,
    clock: Clock,
    pulse: Pulse,
    deadline: float,
    should_stop: Callable[[], bool],
    *,
    cut_when: Callable[[], bool] | None = None,
) -> bool:
    """Cycle the pump until ``deadline``. False if stopped early.

    ``cut_when`` ends the current *burst* early, after which the normal soak
    runs; the deadline still bounds the whole step. That is how a target brew
    pressure is honoured without throttling a pump that cannot be throttled: the
    pump is never left running past the target, but the profile's soak time and
    total length are unchanged. A pump that is already at the target is not
    switched on at all, so a burst cannot become a 20 ms blip.

    The pump is always left off on the way out, including on cancellation. With no
    pump (a valve-only test double) this is a timed wait, so the step still takes
    the time it claims to.
    """
    try:
        while clock.now() < deadline:
            if cut_when is not None and cut_when():
                # Already there: pumping would only be cut off again. Soak for
                # the off time, but always advance the clock (off_s may be zero).
                soak_s = max(pulse.off_s, _TICK_S)
                if not wait_until(clock, min(deadline, clock.now() + soak_s), should_stop):
                    return False
                continue

            if pump is not None:
                pump.set_on(True)
            on_deadline = min(deadline, clock.now() + pulse.on_s)
            if not _burst_until(clock, on_deadline, should_stop, cut_when):
                return False

            if pump is not None:
                pump.set_on(False)
            if not wait_until(clock, min(deadline, clock.now() + pulse.off_s), should_stop):
                return False
        return True
    finally:
        if pump is not None:
            pump.set_on(False)


def _burst_until(
    clock: Clock,
    deadline: float,
    should_stop: Callable[[], bool],
    cut_when: Callable[[], bool] | None,
) -> bool:
    """Run one pump-on burst. False if stopped early by cancellation.

    Sleeps before the first pressure check, so a burst always advances the clock
    even when the pump was just switched on (and even with a zero-length burst).
    """
    while clock.now() < deadline:
        if should_stop():
            return False
        clock.sleep(min(_TICK_S, deadline - clock.now()))
        if cut_when is not None and cut_when():
            return True
    return True
