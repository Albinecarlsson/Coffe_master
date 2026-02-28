import time

from espresso_mod.hal.sim import SimPlant, SimParams
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.shot_runner import ShotRunner


def test_shot_runner_runs_and_closes_valve():
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0))
    control = ControlLoop(plant, plant, plant, hz=50)
    control.start()

    runner = ShotRunner(control=control, valve=plant)
    runner.start("classic_espresso")

    # wait for completion
    for _ in range(200):
        st = runner.status()
        if st.state in ("done", "error", "canceled"):
            break
        time.sleep(0.05)

    st = runner.status()
    assert st.state == "done"
    assert plant.get_open() == 0.0

    control.stop()


def test_shot_runner_cancel():
    plant = SimPlant(initial_c=90.0, params=SimParams(ambient_c=22.0))
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
