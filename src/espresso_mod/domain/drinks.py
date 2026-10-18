"""The drinks the machine can pour.

Pure data: a drink is a target volume of water through the group plus the boiler
temperature it wants. Turning volume into pump seconds is the doser's job,
because that needs the machine's calibrated flow rate.

``water_ml`` is water delivered *through the group*, which is what the pump has
to push -- not the drink in the cup. The puck keeps roughly twice its own weight
in water, so a 9 g dose at 30 ml through the group yields about 12 ml in the cup.
Calibrate against a scale; see docs/renovation.md.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Drink:
    """A selectable drink."""

    key: str
    name: str
    water_ml: float
    setpoint_c: float
    description: str


DRINKS: dict[str, Drink] = {
    drink.key: drink
    for drink in (
        Drink("ristretto", "Ristretto", 20.0, 93.0, "Short and intense"),
        Drink("espresso", "Espresso", 30.0, 93.0, "The everyday single shot"),
        Drink("doppio", "Doppio", 60.0, 93.0, "Double shot, same temperature"),
        Drink("lungo", "Lungo", 55.0, 94.0, "Longer and more extracted"),
    )
}
