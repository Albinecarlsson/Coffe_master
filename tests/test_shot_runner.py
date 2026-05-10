import time

from espresso_mod.hal.sim import SimParams, SimPlant
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.shot_runner import ShotRunner


def test_shot_runner_runs_and_closes_valve():
    # Use fixed_dt for fast, deterministic simulation
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    control = ControlLoop(plant, plant, plant, hz=50)
    control.start()

    runner = ShotRunner(control=control, valve=plant)
    runner.start("classic_espresso")

    # wait for completion - classic_espresso is 28s, with 50Hz control and 0.05s sleep
    # we need enough iterations. Let's wait up to 30 real seconds.
    for _ in range(600):
        st = runner.status()
        if st.state in ("done", "error", "canceled"):
            break
        time.sleep(0.05)

    st = runner.status()
    assert st.state == "done"
    assert plant.get_open() == 0.0

    control.stop()


def test_shot_runner_cancel():
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    control = ControlLoop(plant, plant, plant, hz=50)
    control.start()

    runner = ShotRunner(control=control, valve=plant)
    runner.start("lungo")
    time.sleep(0.2)
    runner.cancel()

    for _ in range(200):
        st = runner.status()
        if st.state in ("canceled", "done", "error"):
            break
        time.sleep(0.05)

    st = runner.status()
    assert st.state == "canceled"
    assert plant.get_open() == 0.0

    control.stop()
