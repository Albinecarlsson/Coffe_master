from __future__ import annotations
import time
import threading

from espresso_mod.domain.pid import PID
from espresso_mod.hal.base import TemperatureSensor, HeaterActuator, ValveActuator

class ControlLoop:
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
        self._stop = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        period = 1.0 / max(1, self.hz)
        last = time.monotonic()
        while not self._stop:
            now = time.monotonic()
            dt = max(0.0, now - last)
            last = now

            reading = self.sensor.read()
            with self._lock:
                enabled = self.enabled
                sp = self.setpoint_c

            if not reading.ok:
                # fail-safe: heater off
                self.heater.set_power(0.0)
            elif enabled:
                power = self.pid.update(sp, reading.celsius, dt)
                self.heater.set_power(power)
            else:
                self.heater.set_power(0.0)

            time.sleep(period)

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if enabled and not self.enabled:
                self.pid.reset()
            self.enabled = enabled

    def set_setpoint(self, setpoint_c: float) -> None:
        with self._lock:
            self.setpoint_c = setpoint_c
