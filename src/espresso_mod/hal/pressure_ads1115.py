"""ADS1115 ADC driver for a ratiometric brew-pressure transducer.

The ADS1115 is a 16-bit, 4-channel I2C ADC. A 0–16 bar sender outputs 0.5–4.5 V
on its 5 V supply, which is more than the Pi or the ADC (run at 3.3 V) can take,
so the signal goes through a 2:1 divider first. Configure the divider with
``PRESSURE_DIVIDER``; the conversion maths lives in
:mod:`espresso_mod.domain.pressure`.

The chip is left in **continuous-conversion** mode at 128 SPS, so
:meth:`Ads1115Pressure.read_pressure` is a two-byte register read instead of a
blocking ~8 ms single-shot conversion. Both the controller's telemetry thread and
the web API read it, and neither should wait on an ADC.

This module is import-safe on a development machine: ``smbus2`` is imported
lazily inside :func:`open_i2c`, never at module import time.
"""

from __future__ import annotations

import contextlib
from typing import Protocol, cast

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.domain.pressure import PressureTransducer
from espresso_mod.hal.base import PressureReading, PressureSensor

_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01

# Config register bits
_OS_START = 0x8000
_MODE_CONTINUOUS = 0x0000
_COMPARATOR_OFF = 0x0003  # disable the ALERT/RDY comparator

# MUX 100..111 select AIN0..AIN3 against GND.
_MUX_SINGLE_ENDED_BASE = 0b100

_PGA_BITS = {6.144: 0b000, 4.096: 0b001, 2.048: 0b010, 1.024: 0b011, 0.512: 0b100, 0.256: 0b101}
_DATA_RATE_BITS = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011, 128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}

_ADC_FULL_SCALE = 32768.0

# The sender's output window, widened by tolerance. Outside it the ADC is seeing
# an unplugged wire, a short, or a sender that is not powered.
_MIN_SENSOR_VOLTS = 0.2
_MAX_SENSOR_VOLTS = 4.8

# Two conversions at 128 SPS, plus margin, before the first sample is believable.
_WARMUP_CONVERSIONS = 2.0
_WARMUP_MARGIN_S = 0.005


class I2CBus(Protocol):
    """The slice of ``smbus2.SMBus`` this driver needs."""

    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None: ...

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]: ...


class Ads1115Pressure(PressureSensor):
    """Brew-pressure sensor backed by an ADS1115 over I2C.

    Every failure -- a bus error, an implausible voltage, or the first conversion
    after startup -- is returned as ``ok=False`` with a reason in ``fault``; the
    ``bar`` field is meaningless in that case.

    Args:
        bus: object exposing ``smbus2``-style block read/write methods.
        address: I2C address, 0x48 (default) to 0x4B.
        channel: single-ended input AIN0..AIN3.
        transducer: the sender's electrical characteristics.
        pga_volts: programmable-gain full scale. ±4.096 V covers the halved
            signal with headroom; do not set it below the signal you expect.
        data_rate: conversions per second (8..860).
        clock: time source, injected so the warm-up window is testable.
    """

    def __init__(
        self,
        bus: I2CBus,
        *,
        address: int = 0x48,
        channel: int = 0,
        transducer: PressureTransducer | None = None,
        pga_volts: float = 4.096,
        data_rate: int = 128,
        clock: Clock | None = None,
    ) -> None:
        if not 0x48 <= address <= 0x4B:
            raise ValueError(f"ADS1115 address must be 0x48..0x4B, got 0x{address:02X}")
        if channel not in (0, 1, 2, 3):
            raise ValueError(f"channel must be 0..3, got {channel}")
        if pga_volts not in _PGA_BITS:
            raise ValueError(f"pga_volts must be one of {sorted(_PGA_BITS)}, got {pga_volts}")
        if data_rate not in _DATA_RATE_BITS:
            raise ValueError(
                f"data_rate must be one of {sorted(_DATA_RATE_BITS)}, got {data_rate}"
            )

        self._bus = bus
        self._address = address
        self._transducer = transducer or PressureTransducer()
        self._pga_volts = float(pga_volts)
        self._data_rate = data_rate
        self._clock: Clock = clock or SystemClock()

        self._config = (
            _OS_START
            | ((_MUX_SINGLE_ENDED_BASE + channel) << 12)
            | (_PGA_BITS[pga_volts] << 9)
            | _MODE_CONTINUOUS
            | (_DATA_RATE_BITS[data_rate] << 5)
            | _COMPARATOR_OFF
        )
        self._bus.write_i2c_block_data(
            self._address, _REG_CONFIG, [(self._config >> 8) & 0xFF, self._config & 0xFF]
        )
        self._ready_at = self._clock.now() + _WARMUP_CONVERSIONS / data_rate + _WARMUP_MARGIN_S

    # ---- sampling ----

    def read_pressure(self) -> PressureReading:
        if self._clock.now() < self._ready_at:
            return PressureReading(bar=0.0, ok=False, fault="ADS1115 warming up")

        try:
            raw = self._bus.read_i2c_block_data(self._address, _REG_CONVERSION, 2)
        except OSError as e:
            return PressureReading(bar=0.0, ok=False, fault=f"I2C read failed: {e}")

        if len(raw) < 2:
            return PressureReading(
                bar=0.0, ok=False, fault=f"short I2C read ({len(raw)} bytes, expected 2)"
            )

        value = int.from_bytes(bytes(raw[:2]), "big", signed=True)
        adc_volts = value * self._pga_volts / _ADC_FULL_SCALE
        sensor_volts = self._transducer.sensor_volts(adc_volts)

        if sensor_volts < _MIN_SENSOR_VOLTS:
            return PressureReading(
                bar=0.0,
                ok=False,
                fault=(
                    f"pressure signal {sensor_volts:.2f} V is below "
                    f"{_MIN_SENSOR_VOLTS:.1f} V (sender unplugged?)"
                ),
            )
        if sensor_volts > _MAX_SENSOR_VOLTS:
            return PressureReading(
                bar=0.0,
                ok=False,
                fault=(
                    f"pressure signal {sensor_volts:.2f} V is above "
                    f"{_MAX_SENSOR_VOLTS:.1f} V (wiring or divider fault)"
                ),
            )

        return PressureReading(bar=self._transducer.bar(adc_volts), ok=True)

    def close(self) -> None:
        """Release the I2C handle, if the bus owns one."""
        close = getattr(self._bus, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                close()


def open_i2c(bus: int = 1) -> I2CBus:  # pragma: no cover - Raspberry Pi only
    """Open the Pi's I2C bus. Lazy-imports ``smbus2`` so this module stays safe."""
    import smbus2

    return cast(I2CBus, smbus2.SMBus(bus))


def open_sensor(  # pragma: no cover - Raspberry Pi only
    *,
    i2c_bus: int = 1,
    address: int = 0x48,
    channel: int = 0,
    bar_max: float = 16.0,
    volts_min: float = 0.5,
    volts_max: float = 4.5,
    divider: float = 2.0,
    pga_volts: float = 4.096,
    data_rate: int = 128,
    clock: Clock | None = None,
) -> Ads1115Pressure:
    """Open the I2C bus and return a configured :class:`Ads1115Pressure`."""
    return Ads1115Pressure(
        open_i2c(i2c_bus),
        address=address,
        channel=channel,
        transducer=PressureTransducer(
            bar_max=bar_max,
            volts_min=volts_min,
            volts_max=volts_max,
            divider=divider,
        ),
        pga_volts=pga_volts,
        data_rate=data_rate,
        clock=clock,
    )
