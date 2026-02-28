from espresso_mod.domain.pid import PID

def test_pid_output_clamped():
    pid = PID(kp=10, ki=0, kd=0)
    out = pid.update(setpoint=100, measured=0, dt=0.1)
    assert 0.0 <= out <= 1.0
    assert out == 1.0

def test_pid_integral_limits():
    pid = PID(kp=0, ki=10, kd=0, integrator_min=-0.1, integrator_max=0.1)
    for _ in range(100):
        pid.update(setpoint=10, measured=0, dt=0.1)
    # integral should saturate, output clamped too
    out = pid.update(setpoint=10, measured=0, dt=0.1)
    assert out == 1.0
