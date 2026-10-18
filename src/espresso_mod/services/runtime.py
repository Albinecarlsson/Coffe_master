from __future__ import annotations

from espresso_mod.config import settings
from espresso_mod.domain.clock import Clock
from espresso_mod.hal.base import HeaterActuator, TemperatureSensor, ValveActuator
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.shot_runner import ShotRunner
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler


class Runtime:
    def __init__(self, clock: Clock | None = None) -> None:
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
            # The MAX31865 sensor driver itself is implemented (see
            # hal/rtd_max31865.py), but the actuators are not: only the thermal
            # simulator provides a heater and valve. Raise before touching SPI so
            # the message is the same on a dev machine and on a Pi.
            raise RuntimeError(
                "HARDWARE_MODE=rtd: the MAX31865 RTD driver is implemented, but the "
                "GPIO heater and valve actuators are not. Use HARDWARE_MODE=sim."
            )
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
        self.shots = ShotRunner(control=self.control, valve=self.valve, clock=clock)

    def stop(self) -> None:
        """Stop every background thread this runtime started."""
        self.shots.cancel()
        self.telemetry_sampler.stop()
        self.control.stop()
