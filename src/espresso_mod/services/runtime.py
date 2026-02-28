from __future__ import annotations

from espresso_mod.config import settings
from espresso_mod.hal.sim import SimPlant, SimParams
from espresso_mod.hal.rtd_max31865 import Max31865RtdSensor
from espresso_mod.hal.base import HeaterActuator, TemperatureSensor, ValveActuator
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler
from espresso_mod.services.shot_runner import ShotRunner


class Runtime:
    def __init__(self) -> None:
        self.sensor: TemperatureSensor
        self.heater: HeaterActuator
        self.valve: ValveActuator

        if settings.hardware_mode == "sim":
            plant = SimPlant(
                initial_c=settings.sim_initial_water_c,
                params=SimParams(ambient_c=settings.sim_ambient_c),
            )
            self.sensor = plant
            self.heater = plant
            self.valve = plant
        elif settings.hardware_mode == "rtd":
            self.sensor = Max31865RtdSensor()
            raise RuntimeError("HARDWARE_MODE=rtd not fully wired yet. Use sim for development.")
        else:
            raise ValueError(f"Unknown HARDWARE_MODE={settings.hardware_mode}")

        self.control = ControlLoop(self.sensor, self.heater, self.valve, hz=settings.control_loop_hz)
        self.control.start()

        # Telemetry
        self.telemetry = TelemetryBuffer(maxlen=20_000)
        self.telemetry_sampler = TelemetrySampler(
            sensor=self.sensor,
            heater=self.heater,
            valve=self.valve,
            buffer=self.telemetry,
            get_setpoint_c=lambda: self.control.setpoint_c,
            get_control_enabled=lambda: self.control.enabled,
            hz=settings.control_loop_hz,
        )
        self.telemetry_sampler.start()

        # Shot runner (non-blocking)
        self.shots = ShotRunner(control=self.control, valve=self.valve)
