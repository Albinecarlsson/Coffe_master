from __future__ import annotations

import time

import pytest

from espresso_mod.domain.drinks import DRINKS, Drink
from espresso_mod.services.doser import Doser


class FakeValve:
    def __init__(self, *, explode_on_open: bool = False, explode_always: bool = False) -> None:
        self.events: list[str] = []
        self.open = 0.0
        self.closed = False
        self._explode_on_open = explode_on_open
        self._explode_always = explode_always

    def set_open(self, open_0_to_1: float) -> None:
        demand = float(open_0_to_1)
        if self._explode_always or (self._explode_on_open and demand > 0.0):
            raise OSError("valve line gone")
        self.open = demand
        self.events.append("open" if self.open else "shut")

    def get_open(self) -> float:
        return self.open

    def close(self) -> None:
        self.closed = True


class FakePump:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.on = False

    def set_on(self, on: bool) -> None:
        self.on = bool(on)
        self.events.append("on" if self.on else "off")

    def get_on(self) -> bool:
        return self.on


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.001)
    return predicate()


def _drink(water_ml: float = 30.0) -> Drink:
    return Drink("test", "Test", water_ml, 93.0, "A drink for tests")


# ---- volume maths ----


def test_duration_is_volume_over_flow():
    doser = Doser(FakeValve(), brew_flow_ml_s=2.0)

    assert doser.duration_s(_drink(30.0)) == pytest.approx(15.0)


@pytest.mark.parametrize("flow", [0.0, -1.0])
def test_non_positive_flow_is_rejected(flow):
    with pytest.raises(ValueError, match="brew_flow_ml_s"):
        Doser(FakeValve(), brew_flow_ml_s=flow)


def test_status_starts_idle_and_closed():
    valve = FakeValve()
    doser = Doser(valve)

    status = doser.status()

    assert status.state == "idle"
    assert status.drink is None
    assert status.delivered_ml == 0.0
    assert valve.open == 0.0


# ---- a whole pour, on virtual time ----


def test_a_pour_delivers_the_drinks_volume(fake_clock):
    valve = FakeValve()
    doser = Doser(valve, brew_flow_ml_s=2.0, clock=fake_clock)
    drink = _drink(30.0)

    doser.start(drink)

    assert _wait_until(lambda: doser.status().state == "done")
    status = doser.status()
    assert status.target_ml == 30.0
    assert status.delivered_ml == pytest.approx(30.0)
    # the loop wakes every tick, so it stops within one tick of the target
    assert status.elapsed_s == pytest.approx(15.0, abs=0.05)
    assert status.message == "Poured 30 ml"
    # the path is shut again once the volume is in the cup
    assert valve.open == 0.0
    assert valve.events[0] == "open"
    assert valve.events[-1] == "shut"


def test_the_pump_runs_for_the_pour_and_stops_first(fake_clock):
    valve = FakeValve()
    pump = FakePump()
    doser = Doser(valve, pump=pump, clock=fake_clock)

    doser.start(_drink(10.0))
    assert _wait_until(lambda: doser.status().state == "done")

    assert pump.events == ["on", "off"]
    # valve opens before the pump pushes, and the pump stops before the valve shuts
    assert valve.events == ["open", "shut"]
    assert not pump.on


def test_every_catalogue_drink_pours_its_own_volume(fake_clock):
    valve = FakeValve()
    doser = Doser(valve, clock=fake_clock)

    for drink in DRINKS.values():
        doser.start(drink)
        assert _wait_until(lambda: doser.status().state == "done")
        assert doser.status().target_ml == drink.water_ml
        assert doser.status().delivered_ml == pytest.approx(drink.water_ml)


# ---- safety ----


def test_a_second_pour_is_refused_while_one_is_running():
    doser = Doser(FakeValve(), brew_flow_ml_s=0.05)
    try:
        doser.start(_drink(10.0))

        with pytest.raises(RuntimeError, match="already running"):
            doser.start(_drink(10.0))
    finally:
        doser.stop()


def test_cancel_stops_the_pour_and_shuts_the_path():
    valve = FakeValve()
    doser = Doser(valve, brew_flow_ml_s=0.05)
    try:
        doser.start(_drink(100.0))
        assert _wait_until(lambda: doser.status().state == "pouring")

        doser.cancel()

        assert _wait_until(lambda: doser.status().state == "canceled")
        assert doser.status().message == "Canceled by user"
        # stopped well before the target volume
        assert doser.status().delivered_ml < 100.0
        assert valve.open == 0.0
    finally:
        doser.stop()


def test_a_valve_failure_reports_an_error_and_leaves_the_path_shut():
    valve = FakeValve(explode_on_open=True)
    pump = FakePump()
    doser = Doser(valve, pump=pump, clock=None)

    doser.start(_drink(30.0))

    assert _wait_until(lambda: doser.status().state == "error")
    assert "OSError" in (doser.status().message or "")
    assert valve.open == 0.0
    assert not pump.on


def test_a_valve_that_also_fails_to_close_never_raises():
    """Closing runs from `finally` and from shutdown, so it must not raise."""
    valve = FakeValve(explode_always=True)
    pump = FakePump()
    doser = Doser(valve, pump=pump)

    doser.start(_drink(30.0))

    assert _wait_until(lambda: doser.status().state == "error")
    assert not pump.on  # the pump still stopped
    doser.stop()  # and shutdown is not blocked


def test_stop_is_safe_when_nothing_is_pouring():
    valve = FakeValve()
    doser = Doser(valve)

    doser.stop()

    assert doser.status().state == "idle"
    assert valve.open == 0.0


def test_stop_waits_for_a_running_pour_and_shuts_the_path():
    valve = FakeValve()
    doser = Doser(valve, brew_flow_ml_s=0.05)
    try:
        doser.start(_drink(100.0))
        assert _wait_until(lambda: doser.status().state == "pouring")

        doser.stop()

        assert doser.status().state == "canceled"
        assert valve.open == 0.0
    finally:
        doser.stop()
