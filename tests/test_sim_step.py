from espresso_mod.hal.sim import SimPlant, SimParams

def test_sim_heats_up_with_power():
    plant = SimPlant(initial_c=25.0, params=SimParams(ambient_c=22.0))
    t0 = plant.read().celsius
    plant.set_power(1.0)
    for _ in range(50):
        plant.read()
    t1 = plant.read().celsius
    assert t1 > t0

def test_sim_cools_more_with_valve_open():
    p = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0))
    p.set_power(0.0)
    p.set_open(0.0)
    t_closed = p.read().celsius
    for _ in range(80):
        p.read()
    t_closed2 = p.read().celsius

    q = SimPlant(initial_c=95.0, params=SimParams(ambient_c=22.0))
    q.set_power(0.0)
    q.set_open(1.0)
    for _ in range(80):
        q.read()
    t_open2 = q.read().celsius

    assert t_open2 < t_closed2
    assert t_closed2 < t_closed
