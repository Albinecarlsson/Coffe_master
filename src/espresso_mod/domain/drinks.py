"""The drinks the machine can pour.

Pure data: a drink is a target volume of water through the group plus the boiler
temperature it wants. Turning volume into pump seconds is the doser's job,
because that needs the machine's calibrated flow rate.

``water_ml`` is water delivered *through the group*, which is what the pump has
to push -- not the drink in the cup. The puck keeps roughly twice its own weight
in water, so a 9 g dose at 30 ml through the group yields about 12 ml in the cup.
Calibrate against a scale; see docs/renovation.md.

``preinfusion`` and ``preinfusion_s`` go together: the pump is pulsed for that
long before the measured pour starts. The water it pushes is not counted against
``water_ml``, because most of it stays in the puck.
"""

from __future__ import annotations

from dataclasses import dataclass

from espresso_mod.domain.pulse import Pulse

# One pattern for every drink: a short burst, then a soak long enough for the
# water to spread through the puck. Tune on the bench.
PREINFUSION = Pulse(on_s=1.5, off_s=1.5)
PREINFUSION_S = 6.0


@dataclass(frozen=True)
class Drink:
    """A selectable drink."""

    key: str
    name: str
    water_ml: float
    setpoint_c: float
    description: str
    preinfusion: Pulse | None = None
    preinfusion_s: float = 0.0


DRINKS: dict[str, Drink] = {
    drink.key: drink
    for drink in (
        Drink(
            "ristretto",
            "Ristretto",
            20.0,
            93.0,
            "Short and intense",
            PREINFUSION,
            PREINFUSION_S,
        ),
        Drink(
            "espresso",
            "Espresso",
            30.0,
            93.0,
            "The everyday single shot",
            PREINFUSION,
            PREINFUSION_S,
        ),
        Drink(
            "doppio",
            "Doppio",
            60.0,
            93.0,
            "Double shot, same temperature",
            PREINFUSION,
            PREINFUSION_S,
        ),
        Drink(
            "lungo",
            "Lungo",
            55.0,
            94.0,
            "Longer and more extracted",
            PREINFUSION,
            PREINFUSION_S,
        ),
    )
}
