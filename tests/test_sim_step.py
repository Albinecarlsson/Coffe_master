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


def test_the_sim_builds_pressure_while_water_flows():
    plant = SimPlant(initial_c=95.0, params=SimParams(fixed_dt=0.05))
    plant.set_open(1.0)

    for _ in range(60):  # 3 s, several rise time constants
        plant.read()

    assert plant.read_pressure().bar > 8.5


def test_the_pressure_bleeds_off_when_the_pump_stops():
    plant = SimPlant(initial_c=95.0, params=SimParams(fixed_dt=0.05))
    plant.set_open(1.0)
    for _ in range(60):
        plant.read()

    plant.set_on(False)
    for _ in range(40):  # 2 s
        plant.read()

    assert plant.read_pressure().bar < 0.5


def test_the_pressure_stays_at_zero_with_the_valve_closed():
    plant = SimPlant(initial_c=95.0, params=SimParams(fixed_dt=0.05))

    for _ in range(40):
        plant.read()

    assert plant.read_pressure().bar < 0.2


def test_the_sim_pressure_pulses_with_the_pump():
    """Preinfusion pulses the pump; the pressure trace should pulse too."""
    plant = SimPlant(initial_c=95.0, params=SimParams(fixed_dt=0.05))
    plant.set_open(1.0)

    for _ in range(20):
        plant.read()
    high = plant.read_pressure().bar

    plant.set_on(False)
    for _ in range(20):
        plant.read()
    low = plant.read_pressure().bar

    assert high > 3.0
    assert low < high / 2
