from __future__ import annotations

import contextlib
import threading
import time

from espresso_mod.domain.pid import PID
from espresso_mod.hal.base import HeaterActuator, TemperatureSensor, ValveActuator

# A stalled loop must not hand the PID a huge dt, or the integral term jumps and
# the element overshoots on the next tick.
_MAX_DT_S = 1.0


class ControlLoop:
    """Runs the PID on a background thread.

    Safety:
        Any exception raised by a sensor or actuator cuts the element, is recorded
        in :attr:`last_error` and does not stop the loop. A loop that dies silently
        while ``enabled`` is still ``True`` is worse than one that keeps trying:
        the UI would claim to be controlling with no heat going in, and only a
        restart would fix it.
    """

    def __init__(
        self,
        sensor: TemperatureSensor,
        heater: HeaterActuator,
        valve: ValveActuator,
        hz: int = 10,
    ) -> None:
        self.sensor = sensor
        self.heater = heater
        self.valve = valve
        self.hz = hz

        self.setpoint_c = 93.0
        self.enabled = False

        # conservative starter gains; tune later
        self.pid = PID(kp=0.08, ki=0.02, kd=0.01, integrator_min=-0.5, integrator_max=0.5)

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

        self._last_error: str | None = None
        self._error_count = 0

    # ---- diagnostics ----

    @property
    def last_error(self) -> str | None:
        """The last loop fault, or None if the most recent tick succeeded."""
        with self._lock:
            return self._last_error

    @property
    def error_count(self) -> int:
        """Total faults since construction, for diagnostics."""
        with self._lock:
            return self._error_count

    # ---- lifecycle ----

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def is_alive(self) -> bool:
        """True while the control thread is running.

        A dead loop with ``enabled`` still true would otherwise look healthy from
        the outside, so this is what a supervisor should check.
        """
        return bool(self._thread and self._thread.is_alive())

    # ---- loop ----

    def _run(self) -> None:
        period = 1.0 / max(1, self.hz)
        last = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            dt = min(_MAX_DT_S, max(0.0, now - last))
            last = now

            self._tick(dt)
            self._stop.wait(period)

    def _tick(self, dt: float) -> None:
        """One control iteration. Never raises.

        Kept separate from the thread so a fault can be tested without waiting on
        a real clock. ``dt`` is clamped so a stalled loop cannot hand the PID a
        huge step.
        """
        dt = min(_MAX_DT_S, max(0.0, dt))
        try:
            reading = self.sensor.read()
            with self._lock:
                enabled = self.enabled
                setpoint_c = self.setpoint_c

            if not reading.ok:
                # fail-safe: heater off
                self.heater.set_power(0.0)
            elif enabled:
                power = self.pid.update(setpoint_c, reading.celsius, dt)
                self.heater.set_power(power)
            else:
                self.heater.set_power(0.0)
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._last_error = f"{type(e).__name__}: {e}"
                self._error_count += 1
            # The element stays off even if this is the call that failed. The SSR
            # driver's command watchdog is the second line of defence.
            with contextlib.suppress(Exception):
                self.heater.set_power(0.0)
        else:
            with self._lock:
                self._last_error = None

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if enabled and not self.enabled:
                self.pid.reset()
            self.enabled = enabled

    def set_setpoint(self, setpoint_c: float) -> None:
        with self._lock:
            self.setpoint_c = setpoint_c
