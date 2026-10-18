from __future__ import annotations

from espresso_mod.domain.drinks import DRINKS


def test_catalogue_is_keyed_by_each_drink_s_own_key():
    assert DRINKS
    for key, drink in DRINKS.items():
        assert key == drink.key


def test_expected_drinks_are_present():
    assert set(DRINKS) == {"ristretto", "espresso", "doppio", "lungo"}


def test_every_drink_is_pourable_and_drinkable():
    for drink in DRINKS.values():
        assert drink.name
        assert drink.description
        assert 0.0 < drink.water_ml <= 200.0
        # Espresso range only: a drink must never ask the boiler for steam
        # temperatures, or the first shot would scald.
        assert 80.0 <= drink.setpoint_c <= 100.0


def test_volume_grows_with_the_drink():
    volumes = [DRINKS[key].water_ml for key in ("ristretto", "espresso", "doppio")]

    assert volumes == sorted(volumes)
