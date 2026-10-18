"""MAX31865 RTD-to-digital converter driver (PT100 / PT1000).

Register map, configuration bits and fault decoding follow the MAX31865
datasheet; the resistance-to-temperature maths lives in
:mod:`espresso_mod.domain.rtd`.

The chip is left in **auto-convert** mode: it converts continuously at the
mains-rejection rate, so :meth:`Max31865RtdSensor.read` is a fast register
access instead of a ~75 ms blocking wait. That matters because both the control
loop and the telemetry sampler call ``read()``.

This module is import-safe on a development machine: ``spidev`` is imported
lazily inside :func:`open_spi`, never at module import time.
"""

from __future__ import annotations

from typing import Protocol, cast

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.domain.rtd import (
    MAX_CELSIUS,
    MIN_CELSIUS,
    PT100_R0,
    celsius_to_resistance,
    resistance_to_celsius,
)
from espresso_mod.hal.base import TemperatureSensor, TempReading

# Registers
_REG_CONFIG = 0x00
_REG_RTD_MSB = 0x01
_REG_RTD_LSB = 0x02
_REG_FAULT_STATUS = 0x07

_READ_ADDRESS_MASK = 0x7F
_WRITE_BIT = 0x80

# Configuration register bits
_CFG_VBIAS_ON = 0x80
_CFG_AUTO_CONVERT = 0x40
_CFG_THREE_WIRE = 0x10
_CFG_FAULT_CLEAR = 0x02
_CFG_FILTER_50HZ = 0x01

# Fault status register bits
_FAULT_HIGH_THRESHOLD = 0x80
_FAULT_LOW_THRESHOLD = 0x40
_FAULT_REFIN_HIGH = 0x20
_FAULT_REFIN_LOW = 0x10
_FAULT_RTDIN_LOW = 0x08
_FAULT_OVERVOLTAGE = 0x04

_FAULT_DESCRIPTIONS = (
    (_FAULT_HIGH_THRESHOLD, "RTD above the high fault threshold (open circuit?)"),
    (_FAULT_LOW_THRESHOLD, "RTD below the low fault threshold (short circuit?)"),
    (_FAULT_REFIN_HIGH, "REFIN- above 0.85 x VBIAS (open RTD or wrong Rref)"),
    (_FAULT_REFIN_LOW, "REFIN- below 0.85 x VBIAS while FORCE- is open"),
    (_FAULT_RTDIN_LOW, "RTDIN- below 0.85 x VBIAS while FORCE- is open"),
    (_FAULT_OVERVOLTAGE, "input overvoltage or undervoltage"),
)

# The 16-bit reading is 15 bits of ADC plus a fault bit in LSB position.
_ADC_FULL_SCALE = 32768.0
_RTD_FAULT_BIT = 0x01

# Datasheet timings: BIAS must settle before a conversion, and a conversion
# needs 62.5 ms in 50 Hz filter mode or 52 ms in 60 Hz mode.
_BIAS_SETTLE_S = 0.010
_CONVERSION_TIME_S = {50: 0.065, 60: 0.055}

_DEFAULT_REFERENCE_OHMS = 430.0


class SpiBus(Protocol):
    """The slice of ``spidev.SpiDev`` this driver needs."""

    def xfer2(self, data: list[int]) -> list[int]: ...


class Max31865RtdSensor(TemperatureSensor):
    """Temperature sensor backed by a MAX31865 breakout over SPI.

    Every failure -- a chip fault, an implausible resistance, or the first
    conversion after startup -- is returned as ``ok=False`` with a reason in
    ``fault``; the ``celsius`` field is meaningless in that case.

    Args:
        spi: object exposing an spidev-style ``xfer2(list[int]) -> list[int]``.
        r0: RTD nominal resistance -- ``100.0`` for PT100, ``1000.0`` for PT1000.
        rref: reference resistor on the breakout (430 ohm for Adafruit's PT100
            board, 4300 ohm for the PT1000 board).
        wires: 2, 3 or 4. Three-wire probes get lead-resistance compensation.
        filter_hz: mains rejection filter, 50 or 60.
        clock: time source, injected so the warm-up window is testable.
    """

    def __init__(
        self,
        spi: SpiBus,
        *,
        r0: float = PT100_R0,
        rref: float = _DEFAULT_REFERENCE_OHMS,
        wires: int = 2,
        filter_hz: int = 60,
        clock: Clock | None = None,
    ) -> None:
        if wires not in (2, 3, 4):
            raise ValueError(f"wires must be 2, 3 or 4, got {wires}")
        if filter_hz not in _CONVERSION_TIME_S:
            raise ValueError(f"filter_hz must be 50 or 60, got {filter_hz}")
        if r0 <= 0.0 or rref <= 0.0:
            raise ValueError("r0 and rref must be positive")

        self._spi = spi
        self._r0 = float(r0)
        self._rref = float(rref)
        self._wires = wires
        self._filter_hz = filter_hz
        self._clock: Clock = clock or SystemClock()

        # Plausible resistance window, derived from the RTD's standard range.
        # The chip's threshold faults are left unconfigured, so a shorted or
        # disconnected probe is caught here rather than by the hardware.
        self._min_ohms = celsius_to_resistance(MIN_CELSIUS, self._r0)
        self._max_ohms = celsius_to_resistance(MAX_CELSIUS, self._r0)

        self._apply_config()
        # Auto-convert needs one bias settle plus one conversion before the
        # RTD registers hold a real measurement.
        self._ready_at = self._clock.now() + _BIAS_SETTLE_S + _CONVERSION_TIME_S[filter_hz]

    # ---- register access ----

    def _read_register(self, address: int) -> int:
        response = self._spi.xfer2([address & _READ_ADDRESS_MASK, 0x00])
        return int(response[1])

    def _write_register(self, address: int, value: int) -> None:
        self._spi.xfer2([address | _WRITE_BIT, value & 0xFF])

    def _base_config(self) -> int:
        config = _CFG_VBIAS_ON | _CFG_AUTO_CONVERT
        if self._wires == 3:
            config |= _CFG_THREE_WIRE
        if self._filter_hz == 50:
            config |= _CFG_FILTER_50HZ
        return config

    def _apply_config(self) -> None:
        """Write the operating config, clearing any latched fault status on the way."""
        self._write_register(_REG_CONFIG, self._base_config() | _CFG_FAULT_CLEAR)
        self._write_register(_REG_CONFIG, self._base_config())

    def _fault_message(self, status: int) -> str:
        reasons = [text for bit, text in _FAULT_DESCRIPTIONS if status & bit]
        if not reasons:
            return f"MAX31865 reported a fault (status 0x{status:02X})"
        return "; ".join(reasons)

    # ---- sampling ----

    def read(self) -> TempReading:
        raw = (self._read_register(_REG_RTD_MSB) << 8) | self._read_register(_REG_RTD_LSB)

        if raw & _RTD_FAULT_BIT:
            status = self._read_register(_REG_FAULT_STATUS)
            self._apply_config()
            return TempReading(celsius=0.0, ok=False, fault=self._fault_message(status))

        if self._clock.now() < self._ready_at:
            return TempReading(celsius=0.0, ok=False, fault="MAX31865 warming up")

        resistance = (raw >> 1) / _ADC_FULL_SCALE * self._rref
        if not self._min_ohms <= resistance <= self._max_ohms:
            return TempReading(
                celsius=0.0,
                ok=False,
                fault=(
                    f"RTD resistance {resistance:.1f} ohms outside "
                    f"{self._min_ohms:.1f}-{self._max_ohms:.1f} ohms"
                ),
            )

        return TempReading(celsius=resistance_to_celsius(resistance, self._r0), ok=True)


def open_spi(  # pragma: no cover - Raspberry Pi only
    *,
    bus: int = 0,
    device: int = 0,
    max_speed_hz: int = 1_000_000,
    mode: int = 1,
) -> SpiBus:
    """Open the Pi's SPI bus. Lazy-imports ``spidev`` so this module stays safe."""
    import spidev

    spi = spidev.SpiDev()
    spi.open(bus, device)
    spi.max_speed_hz = max_speed_hz
    spi.mode = mode  # the MAX31865 supports modes 1 and 3
    return cast(SpiBus, spi)


def open_sensor(  # pragma: no cover - Raspberry Pi only
    *,
    bus: int = 0,
    device: int = 0,
    r0: float = PT100_R0,
    rref: float = _DEFAULT_REFERENCE_OHMS,
    wires: int = 2,
    filter_hz: int = 60,
    clock: Clock | None = None,
) -> Max31865RtdSensor:
    """Open the SPI bus and return a configured :class:`Max31865RtdSensor`."""
    return Max31865RtdSensor(
        open_spi(bus=bus, device=device),
        r0=r0,
        rref=rref,
        wires=wires,
        filter_hz=filter_hz,
        clock=clock,
    )
