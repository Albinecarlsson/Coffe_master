"""Brew-pressure conversion for a ratiometric transducer.

Most affordable espresso pressure senders are ratiometric: 0.5 V at 0 bar and
4.5 V at their rated pressure, on a 5 V supply. The Pi's ADC cannot see 4.5 V,
so the signal is halved by a resistive divider first (``PRESSURE_DIVIDER=2``).

This module owns the volts-to-bar maths and stays free of hardware, so it can be
tested without an ADC.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PressureTransducer:
    """A linear pressure sender, as seen through an optional divider.

    Args:
        bar_max: the sender's rated span (16 bar is the common cheap option).
        volts_min: output at 0 bar.
        volts_max: output at ``bar_max``.
        divider: how many times larger the sender voltage is than the voltage at
            the ADC. 2.0 for a 10k/10k divider, 1.0 when the ADC can take the
            full span.

    Readings are clamped to ``0..bar_max``: a sender cannot report negative
    pressure, and a voltage outside its span is a wiring fault that the driver
    flags rather than a real reading.
    """

    bar_max: float = 16.0
    volts_min: float = 0.5
    volts_max: float = 4.5
    divider: float = 2.0

    def __post_init__(self) -> None:
        if self.bar_max <= 0.0:
            raise ValueError(f"bar_max must be positive, got {self.bar_max}")
        if self.volts_max <= self.volts_min:
            raise ValueError(
                f"volts_max ({self.volts_max}) must be greater than volts_min ({self.volts_min})"
            )
        if self.divider <= 0.0:
            raise ValueError(f"divider must be positive, got {self.divider}")

    def sensor_volts(self, adc_volts: float) -> float:
        """The voltage at the sender, undoing the divider."""
        return adc_volts * self.divider

    def bar(self, adc_volts: float) -> float:
        """Convert a voltage measured at the ADC into bar."""
        volts = self.sensor_volts(adc_volts)
        span = self.volts_max - self.volts_min
        fraction = (volts - self.volts_min) / span
        return max(0.0, min(self.bar_max, fraction * self.bar_max))
