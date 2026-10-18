from espresso_mod.hal.sim import SimParams, SimPlant


def test_sim_heats_up_with_power():
    plant = SimPlant(initial_c=25.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    t0 = plant.read().celsius
    plant.set_power(1.0)
    for _ in range(50):
        plant.read()
    t1 = plant.read().celsius
    assert t1 > t0

def test_sim_cools_more_with_valve_open():
    p = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    p.set_power(0.0)
    p.set_open(0.0)
    t_closed = p.read().celsius
    for _ in range(80):
        p.read()
    t_closed2 = p.read().celsius

    q = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    q.set_power(0.0)
    q.set_open(1.0)
    for _ in range(80):
        q.read()
    t_open2 = q.read().celsius

    assert t_open2 < t_closed2
    assert t_closed2 < t_closed


def test_the_pump_gates_the_flow():
    """No water moves with the valve open and the pump stopped."""
    off = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    off.set_power(0.0)
    off.set_open(1.0)
    off.set_on(False)
    for _ in range(80):
        off.read()

    on = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0, fixed_dt=0.1))
    on.set_power(0.0)
    on.set_open(1.0)
    for _ in range(80):
        on.read()

    assert off.read().celsius > on.read().celsius


def test_the_pump_starts_on():
    # callers that only drive the valve keep the cooling they always had
    plant = SimPlant(initial_c=25.0, params=SimParams(fixed_dt=0.1))

    assert plant.get_on() is True
