import time

import pytest

from espresso_mod.domain.shot_profiles import SHOT_PROFILES, ShotStep
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.shot_runner import ShotRunner


def _make_runner(clock=None):
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    # The control loop is a dependency only; classic_espresso never changes the
    # setpoint, so there is no need to start its thread for these tests.
    control = ControlLoop(plant, plant, plant, hz=50)
    return ShotRunner(control=control, valve=plant, clock=clock), plant


def _wait_for_state(runner, states, timeout=5.0):
    deadline = time.monotonic() + timeout
    state = runner.status()
    while time.monotonic() < deadline:
        state = runner.status()
        if state.state in states:
            return state
        time.sleep(0.005)
    return state


def test_shot_runner_completes_profile_and_closes_valve(fake_clock):
    runner, plant = _make_runner(clock=fake_clock)

    runner.start("classic_espresso")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    assert state.state == "done"
    assert state.profile == "classic_espresso"
    assert plant.get_open() == 0.0
    # a single full-flow pour, measured on the virtual clock
    assert state.total_elapsed_s == pytest.approx(28.0, abs=0.1)


def test_shot_runner_walks_every_step_and_applies_its_setpoint(fake_clock, monkeypatch):
    """Multi-step profiles still work, even though no built-in one uses them yet."""
    monkeypatch.setitem(
        SHOT_PROFILES,
        "test_two_steps",
        [
            ShotStep(seconds=2.0, valve_open=1.0, setpoint_c=94.0),
            ShotStep(seconds=3.0, valve_open=1.0, setpoint_c=92.0),
        ],
    )
    runner, plant = _make_runner(clock=fake_clock)

    runner.start("test_two_steps")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    assert state.state == "done"
    assert state.step_index == 1
    assert state.total_elapsed_s == pytest.approx(5.0, abs=0.1)
    assert runner.control.setpoint_c == 92.0
    assert plant.get_open() == 0.0


def test_shot_runner_cancel_closes_valve():
    # Cancellation is inherently about interrupting real work, so this test
    # uses the system clock and cancels a long profile almost immediately.
    runner, plant = _make_runner()

    runner.start("lungo")
    time.sleep(0.05)
    runner.cancel()

    state = _wait_for_state(runner, ("canceled", "done", "error"))

    assert state.state == "canceled"
    assert plant.get_open() == 0.0


def test_shot_runner_rejects_second_start(monkeypatch):
    monkeypatch.setitem(SHOT_PROFILES, "test_long", [ShotStep(seconds=5.0, valve_open=1.0)])
    runner, _ = _make_runner()

    runner.start("test_long")
    with pytest.raises(RuntimeError):
        runner.start("test_long")

    runner.cancel()
    assert _wait_for_state(runner, ("canceled", "done", "error")).state == "canceled"


def test_shot_runner_cancel_without_running_shot_is_noop():
    runner, _ = _make_runner()

    runner.cancel()

    assert runner.status().state == "idle"


def test_shot_runner_unknown_profile_raises():
    runner, _ = _make_runner()

    with pytest.raises(KeyError):
        runner.start("does_not_exist")
