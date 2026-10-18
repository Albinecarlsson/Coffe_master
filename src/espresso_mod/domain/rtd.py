"""Callendar-Van Dusen conversion between RTD resistance and temperature.

Pure maths, no I/O, per IEC 60751 and the ANALOG DEVICES AN709 application note.

    R(T) = R0 * (1 + A*T + B*T^2)                  for T >= 0
    R(T) = R0 * (1 + A*T + B*T^2 + C*(T-100)*T^3)  for T <  0
"""

from __future__ import annotations

import math

# IEC 60751 / ITS-90 coefficients.
A = 3.9083e-3
B = -5.775e-7
C = -4.183e-12

PT100_R0 = 100.0
PT1000_R0 = 1000.0

# The standard usable range of a platinum RTD.
MIN_CELSIUS = -200.0
MAX_CELSIUS = 850.0

_MAX_ITERATIONS = 50
_TOLERANCE_OHMS = 1e-8


def celsius_to_resistance(celsius: float, r0: float = PT100_R0) -> float:
    """Resistance in ohms of an RTD at ``celsius``."""
    resistance = r0 * (1.0 + A * celsius + B * celsius * celsius)
    if celsius < 0.0:
        resistance += r0 * C * (celsius - 100.0) * celsius**3
    return resistance


def resistance_to_celsius(resistance: float, r0: float = PT100_R0) -> float:
    """Temperature in celsius for an RTD measuring ``resistance``.

    For T >= 0 the equation is a quadratic and is inverted in closed form. Below
    zero the extra ``C`` term makes it a quartic, so the closed form is used as
    a seed for Newton-Raphson on the full equation.

    Raises:
        ValueError: if ``resistance`` is not physically meaningful for ``r0``.
    """
    if resistance <= 0.0:
        raise ValueError(f"resistance must be positive, got {resistance}")

    discriminant = A * A - 4.0 * B * (1.0 - resistance / r0)
    if discriminant < 0.0:
        raise ValueError(
            f"resistance {resistance} ohms is out of range for r0={r0}"
        )

    estimate = (-A + math.sqrt(discriminant)) / (2.0 * B)
    if estimate >= 0.0:
        return estimate
    return _solve_negative_branch(resistance, r0, estimate)


def _solve_negative_branch(resistance: float, r0: float, seed: float) -> float:
    temperature = min(seed, 0.0)
    for _ in range(_MAX_ITERATIONS):
        error = celsius_to_resistance(temperature, r0) - resistance
        if abs(error) < _TOLERANCE_OHMS:
            break
        temperature -= error / _derivative(temperature, r0)
    return temperature


def _derivative(temperature: float, r0: float) -> float:
    slope = r0 * (A + 2.0 * B * temperature)
    if temperature < 0.0:
        slope += r0 * C * (4.0 * temperature**3 - 300.0 * temperature * temperature)
    return slope
