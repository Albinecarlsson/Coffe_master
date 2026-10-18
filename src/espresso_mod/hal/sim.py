from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from espresso_mod.hal.base import (
    HeaterActuator,
    PressureReading,
    PressureSensor,
    PumpActuator,
    TemperatureSensor,
    TempReading,
    ValveActuator,
)


@dataclass
class SimParams:
    ambient_c: float = 22.0
    # thermal model: dT/dt = heater_gain*power - loss_k*(T-ambient) - flow_k*flow*(T-ambient)
    heater_gain: float = 1.6        # °C/s at power=1 (tune)
    loss_k: float = 0.015           # 1/s
    flow_k: float = 0.06            # 1/s (extra cooling when water flows)
    sensor_noise_sigma: float = 0.05 # °C
    max_temp_c: float = 140.0
    fixed_dt: float | None = None   # If set, use fixed time step instead of wall-clock time
    # Pressure model: first-order rise to this pressure while water flows, and
    # decay to zero when the pump stops or the valve closes.
    brew_pressure_bar: float = 9.0  # bar with the pump on and the valve open
    pressure_rise_s: float = 0.35   # time constant building pressure
    pressure_fall_s: float = 0.18   # time constant bleeding it off
    pressure_noise_sigma: float = 0.06  # bar

class SimPlant(TemperatureSensor, HeaterActuator, ValveActuator, PumpActuator, PressureSensor):
    def __init__(self, initial_c: float, params: SimParams):
        self._t_c = initial_c
        self._power = 0.0
        self._valve = 0.0
        # The pump starts on: before it was modelled, opening the valve was enough
        # to draw water, and callers that only drive the valve must keep working.
        self._pump_on = True
        self._pressure_bar = 0.0
        self._params = params
        self._last_ts = time.monotonic()

    def step(self) -> None:
        if self._params.fixed_dt is not None:
            # Use fixed time step for deterministic testing
            dt = self._params.fixed_dt
        else:
            # Use wall-clock time for real-time simulation
            now = time.monotonic()
            dt = max(0.0, now - self._last_ts)
            self._last_ts = now

        if dt <= 0:
            return

        p = self._params
        # Water only moves when the path is open *and* the pump is running.
        flow = self._valve if self._pump_on else 0.0
        dT = (
            p.heater_gain * self._power
            - p.loss_k * (self._t_c - p.ambient_c)
            - p.flow_k * flow * (self._t_c - p.ambient_c)
        ) * dt

        self._t_c += dT
        self._t_c = max(p.ambient_c, min(self._t_c, p.max_temp_c))

        # Brew pressure follows the flow, with a first-order lag in each
        # direction. Pulsing the pump for preinfusion therefore pulses the
        # pressure, which is what the trace on the dashboard should show.
        flowing = self._pump_on and self._valve > 0.0
        target = p.brew_pressure_bar * (self._valve if flowing else 0.0)
        tau = p.pressure_rise_s if target > self._pressure_bar else p.pressure_fall_s
        alpha = 1.0 - math.exp(-dt / max(1e-3, tau))
        self._pressure_bar += (target - self._pressure_bar) * alpha

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

    # PumpActuator
    def set_on(self, on: bool) -> None:
        self._pump_on = bool(on)

    def get_on(self) -> bool:
        return self._pump_on

    # PressureSensor
    def read_pressure(self) -> PressureReading:
        # No step() here: the temperature read drives the plant clock, and two
        # readers stepping would advance the model twice as fast.
        noise = random.gauss(0.0, self._params.pressure_noise_sigma)
        return PressureReading(bar=max(0.0, self._pressure_bar + noise), ok=True)
