import time

import pytest

from espresso_mod.domain.clock import SystemClock
from espresso_mod.domain.pulse import Pulse
from espresso_mod.domain.shot_profiles import SHOT_PROFILES, ShotStep
from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.shot_runner import ShotRunner


def _make_runner(clock=None, on_finish=None, pump=None):
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    # The control loop is a dependency only; classic_espresso never changes the
    # setpoint, so there is no need to start its thread for these tests.
    control = ControlLoop(plant, plant, plant, hz=50)
    return (
        ShotRunner(
            control=control,
            valve=plant,
            clock=clock,
            pump=pump,
            on_finish=on_finish,
        ),
        plant,
    )


class RecordingPump:
    """Remembers when the pump was switched, so pulsing can be asserted."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.events: list[tuple[float, bool]] = []
        self.on = False

    def set_on(self, on: bool) -> None:
        on = bool(on)
        if on != self.on:
            self.events.append((self.clock.now(), on))
        self.on = on

    def get_on(self) -> bool:
        return self.on

    def transitions(self) -> list[tuple[float, bool]]:
        return list(self.events)


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
    # 6 s of pulsed preinfusion, then 25 s of full flow, on the virtual clock
    assert state.total_elapsed_s == pytest.approx(31.0, abs=0.1)


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


def test_shot_runner_reports_finish_and_ignores_a_failing_callback(fake_clock):
    calls: list[str] = []

    def report() -> None:
        calls.append("reported")
        raise OSError("disk full")

    runner, _ = _make_runner(clock=fake_clock, on_finish=report)

    runner.start("classic_espresso")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    # a failed history write must not turn a finished shot into an error
    assert state.state == "done"
    assert calls == ["reported"]


def test_shot_runner_cancel_closes_valve():
    # Cancellation is inherently about interrupting real work, so this test
    # uses the system clock and cancels a long profile almost immediately.
    pump = RecordingPump(SystemClock())
    runner, plant = _make_runner(pump=pump)

    runner.start("lungo")
    time.sleep(0.05)
    runner.cancel()

    state = _wait_for_state(runner, ("canceled", "done", "error"))

    assert state.state == "canceled"
    assert plant.get_open() == 0.0
    assert not pump.on


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


# ---- pump-driven preinfusion ----


def test_a_pulsed_step_cycles_the_pump(fake_clock, monkeypatch):
    monkeypatch.setitem(
        SHOT_PROFILES,
        "test_pulse",
        [ShotStep(seconds=6.0, valve_open=1.0, pulse=Pulse(on_s=2.0, off_s=1.0))],
    )
    start = fake_clock.now()
    pump = RecordingPump(fake_clock)
    runner, plant = _make_runner(clock=fake_clock, pump=pump)

    runner.start("test_pulse")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    assert state.state == "done"
    # on for 2 s, off for 1 s, on for 2 s, off for the last second of the step
    assert [(ts - start, on) for ts, on in pump.transitions()] == [
        (0.0, True),
        (2.0, False),
        (3.0, True),
        (5.0, False),
    ]
    assert not pump.on
    # the valve is shut once the shot is over, whatever the pump did
    assert plant.get_open() == 0.0


def test_a_dwell_step_keeps_the_pump_off(fake_clock, monkeypatch):
    monkeypatch.setitem(
        SHOT_PROFILES,
        "test_dwell",
        [
            ShotStep(seconds=4.0, valve_open=1.0, pump_on=False),
            ShotStep(seconds=2.0, valve_open=1.0),
        ],
    )
    start = fake_clock.now()
    pump = RecordingPump(fake_clock)
    runner, _ = _make_runner(clock=fake_clock, pump=pump)

    runner.start("test_dwell")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    assert state.state == "done"
    # nothing during the dwell, then continuous flow for the pour
    assert [(ts - start, on) for ts, on in pump.transitions()] == [
        (4.0, True),
        (6.0, False),
    ]
    assert not pump.on


def test_the_pump_runs_continuously_on_a_plain_step(fake_clock, monkeypatch):
    monkeypatch.setitem(
        SHOT_PROFILES,
        "test_plain",
        [ShotStep(seconds=3.0, valve_open=1.0)],
    )
    pump = RecordingPump(fake_clock)
    runner, _ = _make_runner(clock=fake_clock, pump=pump)

    runner.start("test_plain")
    assert _wait_for_state(runner, ("done", "error", "canceled")).state == "done"

    assert [on for _, on in pump.transitions()] == [True, False]
    assert not pump.on


class ExplodingValve:
    def set_open(self, open_0_to_1: float) -> None:
        raise OSError("valve line gone")

    def get_open(self) -> float:
        return 0.0


def test_a_valve_failure_reports_an_error_and_stops_the_pump(fake_clock):
    pump = RecordingPump(fake_clock)
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    runner = ShotRunner(
        control=ControlLoop(plant, plant, plant, hz=50),
        valve=ExplodingValve(),
        clock=fake_clock,
        pump=pump,
    )

    runner.start("classic_espresso")
    state = _wait_for_state(runner, ("done", "error", "canceled"))

    assert state.state == "error"
    assert "OSError" in (state.message or "")
    assert not pump.on

