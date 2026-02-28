import time

from espresso_mod.hal.sim import SimPlant, SimParams
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.telemetry import TelemetryBuffer, TelemetrySampler


def test_telemetry_collects_points():
    plant = SimPlant(initial_c=25.0, params=SimParams(ambient_c=22.0))
    control = ControlLoop(plant, plant, plant, hz=20)
    control.start()

    buf = TelemetryBuffer(maxlen=1000)
    sampler = TelemetrySampler(
        sensor=plant,
        heater=plant,
        valve=plant,
        buffer=buf,
        get_setpoint_c=lambda: control.setpoint_c,
        get_control_enabled=lambda: control.enabled,
        hz=20,
    )
    sampler.start()

    time.sleep(0.2)
    pts = buf.snapshot_last_seconds(5.0)
    assert len(pts) > 0

    sampler.stop()
    control.stop()
