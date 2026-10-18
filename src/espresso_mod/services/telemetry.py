from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from espresso_mod.hal.base import (
    HeaterActuator,
    PressureSensor,
    TemperatureSensor,
    TempReading,
    ValveActuator,
)
from espresso_mod.services.peak import PeakPressure


@dataclass(frozen=True)
class TelemetrySample:
    ts: float  # monotonic seconds
    temp_c: float
    temp_ok: bool
    heater_power: float
    valve_open: float
    setpoint_c: float
    control_enabled: bool
    pressure_bar: float | None = None
    pressure_ok: bool = True


class TelemetryBuffer:
    """
    Thread-safe ring buffer for telemetry samples.
    Stores samples with a monotonic timestamp.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._buf: deque[TelemetrySample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, sample: TelemetrySample) -> None:
        with self._lock:
            self._buf.append(sample)

    def snapshot_last_seconds(self, seconds: float) -> list[TelemetrySample]:
        cutoff = time.monotonic() - max(0.0, seconds)
        with self._lock:
            # iterate from newest backwards, stop when older than cutoff
            out_rev: list[TelemetrySample] = []
            for s in reversed(self._buf):
                if s.ts < cutoff:
                    break
                out_rev.append(s)
            return list(reversed(out_rev))


class TelemetrySampler:
    """
    Background sampler that periodically reads the sensor + actuator state
    and appends it to a TelemetryBuffer.
    """

    def __init__(
        self,
        sensor: TemperatureSensor,
        heater: HeaterActuator,
        valve: ValveActuator,
        buffer: TelemetryBuffer,
        get_setpoint_c: Callable[[], float],
        get_control_enabled: Callable[[], bool],
        hz: int = 10,
        pressure: PressureSensor | None = None,
        peak: PeakPressure | None = None,
    ) -> None:
        self.sensor = sensor
        self.heater = heater
        self.valve = valve
        self.buffer = buffer
        self.get_setpoint_c = get_setpoint_c
        self.get_control_enabled = get_control_enabled
        self.hz = max(1, hz)
        self.pressure = pressure
        self.peak = peak

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

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

    def _run(self) -> None:
        period = 1.0 / self.hz
        while not self._stop.is_set():
            ts = time.monotonic()
            # A sensor that throws must not kill the sampler: losing telemetry
            # also loses the pressure trace and the peak used for history.
            try:
                reading = self.sensor.read()
            except Exception as e:  # noqa: BLE001
                reading = TempReading(celsius=0.0, ok=False, fault=f"{type(e).__name__}: {e}")

            pressure_bar: float | None = None
            pressure_ok = True
            if self.pressure is not None:
                try:
                    pressure = self.pressure.read_pressure()
                except Exception:  # noqa: BLE001
                    pressure_ok = False
                else:
                    pressure_bar = pressure.bar
                    pressure_ok = pressure.ok
                    if pressure.ok and self.peak is not None:
                        self.peak.observe(pressure.bar)

            sample = TelemetrySample(
                ts=ts,
                temp_c=reading.celsius,
                temp_ok=reading.ok,
                heater_power=self.heater.get_power(),
                valve_open=self.valve.get_open(),
                setpoint_c=float(self.get_setpoint_c()),
                control_enabled=bool(self.get_control_enabled()),
                pressure_bar=pressure_bar,
                pressure_ok=pressure_ok,
            )
            self.buffer.append(sample)
            self._stop.wait(period)
