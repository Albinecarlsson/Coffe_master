"""Driving the pump over time, in a way that can be stopped promptly.

Both the shot runner and the doser need "keep doing this until a deadline, or
until someone cancels". Putting it here keeps the 20 ms polling loop in one place
instead of duplicated across two services.
"""

from __future__ import annotations

from collections.abc import Callable

from espresso_mod.domain.clock import Clock
from espresso_mod.domain.pulse import Pulse
from espresso_mod.hal.base import PumpActuator

# How often we come up for air to check for a cancel.
_TICK_S = 0.02


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
) -> bool:
    """Cycle the pump until ``deadline``. False if stopped early.

    The pump is always left off on the way out, including on cancellation. With no
    pump (a valve-only test double) this is a timed wait, so the step still takes
    the time it claims to.
    """
    try:
        while clock.now() < deadline:
            if pump is not None:
                pump.set_on(True)
            if not wait_until(clock, min(deadline, clock.now() + pulse.on_s), should_stop):
                return False

            if pump is not None:
                pump.set_on(False)
            if not wait_until(clock, min(deadline, clock.now() + pulse.off_s), should_stop):
                return False
        return True
    finally:
        if pump is not None:
            pump.set_on(False)
