from __future__ import annotations

from espresso_mod.config import settings
from espresso_mod.domain.clock import Clock
from espresso_mod.hal.base import (
    Closable,
    HeaterActuator,
    PressureSensor,
    PumpActuator,
    TemperatureSensor,
    ValveActuator,
)
from espresso_mod.hal.gpio import GpioHeater, GpioPump, GpioValve, open_output_pin
from espresso_mod.hal.pressure_ads1115 import open_sensor as open_pressure_sensor
from espresso_mod.hal.rtd_max31865 import open_sensor
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.doser import Doser
from espresso_mod.services.history import ShotHistory
from espresso_mod.services.peak import PeakPressure
from espresso_mod.services.shot_runner import ShotRunner
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler


class Runtime:
    def __init__(self, clock: Clock | None = None) -> None:
        self.sensor: TemperatureSensor
        self.heater: HeaterActuator
        self.valve: ValveActuator
        # In sim mode the plant is the pump too, so preinfusion pulsing shows up
        # in the telemetry instead of being a no-op.
        self.pump: PumpActuator | None = None
        # Optional: brew pressure is monitoring only, so a machine without the
        # sender (or with PRESSURE_ENABLED=false) still runs.
        self.pressure: PressureSensor | None = None
        # Devices holding an OS handle (SPI, I2C, GPIO) that shutdown must release.
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
            self.pump = plant
            self.pressure = plant
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

            if settings.pressure_enabled:
                pressure = open_pressure_sensor(
                    i2c_bus=settings.pressure_i2c_bus,
                    address=settings.pressure_i2c_address,
                    channel=settings.pressure_ads_channel,
                    bar_max=settings.pressure_bar_max,
                    volts_min=settings.pressure_volts_min,
                    volts_max=settings.pressure_volts_max,
                    divider=settings.pressure_divider,
                    pga_volts=settings.pressure_ads_pga,
                    data_rate=settings.pressure_ads_data_rate,
                )
                self.pressure = pressure
                self._devices.append(pressure)
        else:
            raise ValueError(f"Unknown HARDWARE_MODE={settings.hardware_mode}")

        self.history = ShotHistory(settings.history_db_path)
        # Reset when a pour starts, read when it is written to history.
        self.pressure_peak = PeakPressure()

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
            pressure=self.pressure,
            peak=self.pressure_peak,
        )
        self.telemetry_sampler.start()

        # Shot runner (non-blocking)
        self.shots = ShotRunner(
            control=self.control,
            valve=self.valve,
            clock=clock,
            pump=self.pump,
            on_start=self.pressure_peak.reset,
            on_finish=self._record_shot,
        )

        # Drink dosing (non-blocking). Shares the injected clock, so tests can
        # drive a whole pour without waiting for it.
        self.doser = Doser(
            self.valve,
            pump=self.pump,
            brew_flow_ml_s=settings.brew_flow_ml_s,
            clock=clock,
            on_start=self.pressure_peak.reset,
            on_finish=self._record_pour,
        )

    # ---- history ----

    def _record_shot(self) -> None:
        state = self.shots.status()
        if state.profile is None or state.started_ts <= 0:
            return
        self.history.record(
            kind="shot",
            name=state.profile,
            state=state.state,
            elapsed_s=state.total_elapsed_s,
            message=state.message,
            peak_bar=self.pressure_peak.bar,
        )

    def _record_pour(self) -> None:
        state = self.doser.status()
        if state.drink is None:
            return
        self.history.record(
            kind="drink",
            name=state.drink,
            state=state.state,
            target_ml=state.target_ml,
            delivered_ml=state.delivered_ml,
            elapsed_s=state.elapsed_s,
            message=state.message,
            peak_bar=self.pressure_peak.bar,
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
