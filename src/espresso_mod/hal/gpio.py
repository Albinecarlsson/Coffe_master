"""GPIO actuators: solid state relay heater and solenoid valve.

The pin is a duck-typed seam (``on()`` / ``off()`` / ``close()``), so these
actuators can be driven by a fake in tests and the GPIO back end can be swapped.
Real pins come from gpiozero, imported lazily by :func:`open_output_pin`.

This module is import-safe on a development machine that has no GPIO at all.
"""

from __future__ import annotations

import threading
from typing import Protocol, cast

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.hal.base import HeaterActuator, PumpActuator, ValveActuator

# A solenoid has two states, so a fractional demand cannot be honoured: any
# demand above this threshold opens it fully. The threshold is a deadband, not a
# throttle. It defaults to zero because refusing a 0.2 demand would silently void
# a profile step; raise it only to suppress demands a caller wants ignored.
_OPEN_THRESHOLD = 0.0

_PIN_CLOSE_TIMEOUT_S = 1.0


class OutputPin(Protocol):
    """A digital output line, energised by ``on()``.

    ``gpiozero.DigitalOutputDevice`` satisfies this; ``active_high`` is handled
    inside the device so ``on()`` always means "energised".
    """

    def on(self) -> None: ...
    def off(self) -> None: ...
    def close(self) -> None: ...


class GpioHeater(HeaterActuator):
    """Heater driver switching a solid state relay by time proportioning.

    A solid state relay is either on or off, so the PID's continuous duty cycle
    is realised by holding the element on for ``duty * window_s`` at the start of
    each window. A one second window is far shorter than a boiler's thermal time
    constant, and switching at around 1 Hz is gentle on the relay.

    The chopper thread starts with the object; :meth:`close` stops it and
    releases the pin.

    Safety:
        The pin is driven low on construction and again on :meth:`close`, and the
        applied duty falls to zero if the caller stops sending commands for
        ``command_timeout_s``. A control loop that stalls or dies must not leave
        the element latched on.
    """

    def __init__(
        self,
        pin: OutputPin,
        *,
        window_s: float = 1.0,
        command_timeout_s: float = 1.0,
        clock: Clock | None = None,
    ) -> None:
        if window_s <= 0.0:
            raise ValueError(f"window_s must be positive, got {window_s}")
        if command_timeout_s <= 0.0:
            raise ValueError(f"command_timeout_s must be positive, got {command_timeout_s}")

        self._pin = pin
        self._window_s = float(window_s)
        self._command_timeout_s = float(command_timeout_s)
        self._clock: Clock = clock or SystemClock()

        self._duty = 0.0
        self._last_command_at = self._clock.now()
        self._window_started_at = self._clock.now()

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

        self._pin.off()
        self._thread.start()

    # ---- HeaterActuator ----

    def set_power(self, power_0_to_1: float) -> None:
        with self._lock:
            self._duty = min(1.0, max(0.0, float(power_0_to_1)))
            self._last_command_at = self._clock.now()

    def get_power(self) -> float:
        """The duty actually being applied, which is zero once commands go stale."""
        with self._lock:
            if self._clock.now() - self._last_command_at > self._command_timeout_s:
                return 0.0
            return self._duty

    # ---- lifecycle ----

    def close(self) -> None:
        """Stop chopping, then drive the pin low and release it."""
        self._stop.set()
        self._thread.join(timeout=_PIN_CLOSE_TIMEOUT_S)
        self._pin.off()
        self._pin.close()

    # ---- chopper ----

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._drive())

    def _drive(self) -> float:
        """Apply the current window, returning the seconds until the next edge.

        Kept separate from the thread so the window arithmetic can be tested
        against a fake clock instead of by timing a real one.
        """
        now = self._clock.now()
        if now - self._window_started_at >= self._window_s:
            # Start a new window, resynchronising if this loop ran late.
            self._window_started_at = now

        on_for = self.get_power() * self._window_s
        elapsed = now - self._window_started_at
        if elapsed < on_for:
            self._pin.on()
            return on_for - elapsed

        self._pin.off()
        return self._window_s - elapsed


class SwitchedOutput:
    """Shared behaviour for a single GPIO output that starts de-energised."""

    def __init__(self, pin: OutputPin) -> None:
        self._pin = pin
        self._on = False
        self._pin.off()

    def get_on(self) -> bool:
        return self._on

    def close(self) -> None:
        """Drive the output low, then release the pin."""
        self._set(False)
        self._pin.close()

    def _set(self, on: bool) -> None:
        self._on = on
        if on:
            self._pin.on()
        else:
            self._pin.off()


class GpioValve(SwitchedOutput, ValveActuator):
    """Solenoid valve driver.

    The valve is binary: any demand above ``open_threshold`` opens it fully, so a
    demand of 0.2 means "some water" rather than 20% flow. See ``_OPEN_THRESHOLD``.
    """

    def __init__(self, pin: OutputPin, *, open_threshold: float = _OPEN_THRESHOLD) -> None:
        super().__init__(pin)
        self._open_threshold = float(open_threshold)

    def set_open(self, open_0_to_1: float) -> None:
        self._set(float(open_0_to_1) > self._open_threshold)

    def get_open(self) -> float:
        return 1.0 if self._on else 0.0


class GpioPump(SwitchedOutput, PumpActuator):
    """Vibration pump driver.

    The pump sits on the mains side behind its own relay or SSR; only the
    switching line is on the Pi. Closing the water path pump-first is the
    caller's job, since a pump pushing against a shut valve has nowhere to go.
    """

    def set_on(self, on: bool) -> None:
        self._set(bool(on))


def open_output_pin(pin: int, *, active_high: bool = True) -> OutputPin:  # pragma: no cover
    """Open a GPIO line as a digital output, starting de-energised.

    Lazy-imports ``gpiozero`` so this module stays importable off a Raspberry Pi.
    """
    from gpiozero import DigitalOutputDevice

    device = DigitalOutputDevice(pin, active_high=active_high, initial_value=False)
    return cast(OutputPin, device)
