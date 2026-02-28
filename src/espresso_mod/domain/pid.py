from __future__ import annotations
from dataclasses import dataclass

@dataclass
class PID:
    kp: float
    ki: float
    kd: float
    integrator_min: float = -1.0
    integrator_max: float = 1.0

    _integral: float = 0.0
    _prev_error: float | None = None

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = None

    def update(self, setpoint: float, measured: float, dt: float) -> float:
        if dt <= 0:
            return 0.0
        error = setpoint - measured
        self._integral += error * dt
        self._integral = max(self.integrator_min, min(self._integral, self.integrator_max))

        derivative = 0.0
        if self._prev_error is not None:
            derivative = (error - self._prev_error) / dt
        self._prev_error = error

        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(0.0, min(1.0, output))
