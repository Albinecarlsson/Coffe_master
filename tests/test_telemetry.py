import time

import pytest

from espresso_mod.hal.base import PressureReading, TempReading
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.peak import PeakPressure
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler


class _Heater:
    def get_power(self) -> float:
        return 0.25


class _Valve:
    def get_open(self) -> float:
        return 0.0


class _FixedSensor:
    def read(self) -> TempReading:
        return TempReading(celsius=93.0)


class _RaisingSensor:
    def read(self) -> TempReading:
        raise OSError("thermometer bus gone")


class _FixedPressure:
    def __init__(self, bar: float) -> None:
        self.bar = bar

    def read_pressure(self) -> PressureReading:
        return PressureReading(bar=self.bar)


class _RaisingPressure:
    def read_pressure(self) -> PressureReading:
        raise OSError("i2c bus gone")


def _sampler(buf: TelemetryBuffer, **kwargs) -> TelemetrySampler:
    kwargs.setdefault("sensor", _FixedSensor())
    kwargs.setdefault("heater", _Heater())
    kwargs.setdefault("valve", _Valve())
    return TelemetrySampler(
        buffer=buf,
        get_setpoint_c=lambda: 93.0,
        get_control_enabled=lambda: True,
        hz=50,
        **kwargs,
    )


def _run_once(sampler: TelemetrySampler, seconds: float = 0.08) -> None:
    sampler.start()
    time.sleep(seconds)
    sampler.stop()


def test_telemetry_collects_points():
    plant = SimPlant(initial_c=25.0, params=SimParams(ambient_c=22.0))
    control = ControlLoop(plant, plant, plant, hz=20)
    control.start()

    buf = TelemetryBuffer(maxlen=1000)
    sampler = TelemetrySampler(
        sensor=plant,
        heater=plant,
        valve=plant,
        buffer=buf,
        get_setpoint_c=lambda: control.setpoint_c,
        get_control_enabled=lambda: control.enabled,
        hz=20,
    )
    sampler.start()

    time.sleep(0.2)
    pts = buf.snapshot_last_seconds(5.0)
    assert len(pts) > 0

    sampler.stop()
    control.stop()


def test_telemetry_includes_pressure_when_a_sender_is_fitted():
    buf = TelemetryBuffer()
    peak = PeakPressure()

    _run_once(_sampler(buf, pressure=_FixedPressure(9.2), peak=peak))

    points = buf.snapshot_last_seconds(5.0)
    assert points
    assert all(point.pressure_ok for point in points)
    assert all(point.pressure_bar == pytest.approx(9.2) for point in points)
    assert peak.bar == pytest.approx(9.2)


def test_telemetry_omits_pressure_without_a_sender():
    buf = TelemetryBuffer()

    _run_once(_sampler(buf))

    points = buf.snapshot_last_seconds(5.0)
    assert points
    assert all(point.pressure_bar is None for point in points)


def test_a_failing_pressure_sensor_does_not_stop_the_sampler():
    buf = TelemetryBuffer()

    _run_once(_sampler(buf, pressure=_RaisingPressure()))

    points = buf.snapshot_last_seconds(5.0)
    assert points
    assert all(point.pressure_ok is False for point in points)
    assert all(point.pressure_bar is None for point in points)
    assert all(point.temp_ok for point in points)


def test_a_failing_thermometer_does_not_stop_the_sampler():
    buf = TelemetryBuffer()

    _run_once(_sampler(buf, sensor=_RaisingSensor()))

    points = buf.snapshot_last_seconds(5.0)
    assert points
    assert all(point.temp_ok is False for point in points)
    # the loop kept running instead of dying on the first exception
    assert len(points) > 1

