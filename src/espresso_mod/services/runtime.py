from __future__ import annotations

from espresso_mod.config import settings
from espresso_mod.domain.clock import Clock
from espresso_mod.hal.base import (
    Closable,
    HeaterActuator,
    PumpActuator,
    TemperatureSensor,
    ValveActuator,
)
from espresso_mod.hal.gpio import GpioHeater, GpioPump, GpioValve, open_output_pin
from espresso_mod.hal.rtd_max31865 import open_sensor
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.doser import Doser
from espresso_mod.services.shot_runner import ShotRunner
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler


class Runtime:
    def __init__(self, clock: Clock | None = None) -> None:
        self.sensor: TemperatureSensor
        self.heater: HeaterActuator
        self.valve: ValveActuator
        # None in sim mode: the plant's valve already stands in for the flow.
        self.pump: PumpActuator | None = None
        # Devices holding an OS handle (SPI, GPIO) that shutdown must release.
        # Empty in sim mode, where the plant is a plain object.
        self._devices: list[Closable] = []

        if settings.hardware_mode == "sim":
            plant = SimPlant(
                initial_c=settings.sim_initial_water_c,
                params=SimParams(ambient_c=settings.sim_ambient_c),
            )
            self.sensor = plant
            self.heater = plant
            self.valve = plant
        elif settings.hardware_mode == "rtd":
            self.sensor = open_sensor(
                bus=settings.rtd_spi_bus,
                device=settings.rtd_spi_device,
                r0=settings.rtd_r0_ohms,
                rref=settings.rtd_rref_ohms,
                wires=settings.rtd_wires,
                filter_hz=settings.rtd_filter_hz,
            )
            self.heater = GpioHeater(
                open_output_pin(settings.heater_gpio_pin, active_high=settings.heater_active_high),
                window_s=settings.heater_window_s,
            )
            self.valve = GpioValve(
                open_output_pin(settings.valve_gpio_pin, active_high=settings.valve_active_high)
            )
            self.pump = GpioPump(
                open_output_pin(settings.pump_gpio_pin, active_high=settings.pump_active_high)
            )
            self._devices = [self.heater, self.valve, self.pump]
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

        # Drink dosing (non-blocking). Shares the injected clock, so tests can
        # drive a whole pour without waiting for it.
        self.doser = Doser(
            self.valve,
            pump=self.pump,
            brew_flow_ml_s=settings.brew_flow_ml_s,
            clock=clock,
        )

    def stop(self) -> None:
        """Stop every background thread this runtime started, then power down.

        The element is cut before the pins are released, so a shutdown can never
        leave the heater energised.
        """
        self.shots.cancel()
        self.doser.stop()
        self.control.stop()
        self.telemetry_sampler.stop()
        self.heater.set_power(0.0)
        for device in self._devices:
            device.close()
