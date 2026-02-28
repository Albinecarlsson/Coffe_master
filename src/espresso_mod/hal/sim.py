from __future__ import annotations
from dataclasses import dataclass
import random
import time

from espresso_mod.hal.base import TempReading, TemperatureSensor, HeaterActuator, ValveActuator

@dataclass
class SimParams:
    ambient_c: float = 22.0
    # thermal model: dT/dt = heater_gain*power - loss_k*(T-ambient) - flow_k*valve*(T-ambient)
    heater_gain: float = 1.6        # °C/s at power=1 (tune)
    loss_k: float = 0.015           # 1/s
    flow_k: float = 0.06            # 1/s (extra cooling when valve open)
    sensor_noise_sigma: float = 0.05 # °C
    max_temp_c: float = 140.0

class SimPlant(TemperatureSensor, HeaterActuator, ValveActuator):
    def __init__(self, initial_c: float, params: SimParams):
        self._t_c = initial_c
        self._power = 0.0
        self._valve = 0.0
        self._params = params
        self._last_ts = time.monotonic()

    def step(self) -> None:
        now = time.monotonic()
        dt = max(0.0, now - self._last_ts)
        self._last_ts = now
        if dt <= 0:
            return

        p = self._params
        dT = (
            p.heater_gain * self._power
            - p.loss_k * (self._t_c - p.ambient_c)
            - p.flow_k * self._valve * (self._t_c - p.ambient_c)
        ) * dt

        self._t_c += dT
        self._t_c = max(p.ambient_c, min(self._t_c, p.max_temp_c))

    # TemperatureSensor
    def read(self) -> TempReading:
        self.step()
        noise = random.gauss(0.0, self._params.sensor_noise_sigma)
        return TempReading(celsius=self._t_c + noise, ok=True)

    # HeaterActuator
    def set_power(self, power_0_to_1: float) -> None:
        self._power = float(min(1.0, max(0.0, power_0_to_1)))

    def get_power(self) -> float:
        return self._power

    # ValveActuator
    def set_open(self, open_0_to_1: float) -> None:
        self._valve = float(min(1.0, max(0.0, open_0_to_1)))

    def get_open(self) -> float:
        return self._valve
