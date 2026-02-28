from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List

from espresso_mod.hal.base import HeaterActuator, TemperatureSensor, ValveActuator


@dataclass(frozen=True)
class TelemetrySample:
    ts: float  # monotonic seconds
    temp_c: float
    temp_ok: bool
    heater_power: float
    valve_open: float
    setpoint_c: float
    control_enabled: bool


class TelemetryBuffer:
    """
    Thread-safe ring buffer for telemetry samples.
    Stores samples with a monotonic timestamp.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._buf: Deque[TelemetrySample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, sample: TelemetrySample) -> None:
        with self._lock:
            self._buf.append(sample)

    def snapshot_last_seconds(self, seconds: float) -> List[TelemetrySample]:
        cutoff = time.monotonic() - max(0.0, seconds)
        with self._lock:
            # iterate from newest backwards, stop when older than cutoff
            out_rev: List[TelemetrySample] = []
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
        get_setpoint_c: callable,
        get_control_enabled: callable,
        hz: int = 10,
    ) -> None:
        self.sensor = sensor
        self.heater = heater
        self.valve = valve
        self.buffer = buffer
        self.get_setpoint_c = get_setpoint_c
        self.get_control_enabled = get_control_enabled
        self.hz = max(1, hz)

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
        period = 1.0 / self.hz
        while not self._stop:
            ts = time.monotonic()
            reading = self.sensor.read()

            sample = TelemetrySample(
                ts=ts,
                temp_c=reading.celsius,
                temp_ok=reading.ok,
                heater_power=self.heater.get_power(),
                valve_open=self.valve.get_open(),
                setpoint_c=float(self.get_setpoint_c()),
                control_enabled=bool(self.get_control_enabled()),
            )
            self.buffer.append(sample)
            time.sleep(period)
