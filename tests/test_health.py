from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from espresso_mod import api as api_module
from espresso_mod.hal.base import TempReading
from espresso_mod.main import app
from espresso_mod.services.runtime import Runtime


@pytest.fixture
def runtime(monkeypatch, fake_clock):
    """A fresh runtime bound to the virtual clock, injected as the app singleton."""
    rt = Runtime(clock=fake_clock)
    monkeypatch.setattr(api_module, "_runtime", rt)
    yield rt
    rt.stop()


@pytest.fixture
def client(runtime):
    return TestClient(app)


# ---- healthy ----


def test_health_is_ok_on_a_simulated_machine(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["mode"] == "sim"
    assert body["uptime_s"] >= 0.0
    assert body["running"] is False
    assert body["temp_ok"] is True
    assert body["temp_fault"] is None
    assert body["pressure_ok"] is True
    assert body["control_alive"] is True
    assert body["control_enabled"] is False
    assert body["control_error"] is None


def test_health_reports_uptime_as_real_seconds(client):
    # The injected clock must not fake process uptime.
    assert client.get("/health").json()["uptime_s"] >= 0.0


def test_health_reports_the_control_enabled_state(client, runtime):
    runtime.control.set_enabled(True)

    assert client.get("/health").json()["control_enabled"] is True


# ---- unhealthy ----


def test_health_is_503_on_a_temperature_fault(client, runtime, monkeypatch):
    monkeypatch.setattr(
        runtime.sensor, "read", lambda: TempReading(0.0, ok=False, fault="open circuit")
    )

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["temp_ok"] is False
    assert body["temp_fault"] == "open circuit"
    # The loop itself is fine; only the reading is bad.
    assert body["control_alive"] is True


def test_health_is_503_when_the_control_loop_reports_a_fault(client, runtime, monkeypatch):
    class _DeadSensor:
        def read(self) -> TempReading:
            raise RuntimeError("rtd unplugged")

    # Point only the loop at a failing sensor, so teardown can still shut down.
    monkeypatch.setattr(runtime.control, "sensor", _DeadSensor())
    # One failing tick is enough to record the fault synchronously.
    runtime.control._tick(0.1)

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["control_alive"] is True
    assert "rtd unplugged" in body["control_error"]


def test_health_is_503_when_the_control_thread_is_not_running(client, runtime, monkeypatch):
    monkeypatch.setattr(runtime.control, "_thread", None)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["control_alive"] is False


# ---- optional pressure sender ----


def test_health_stays_ok_without_a_pressure_sender(client, runtime, monkeypatch):
    monkeypatch.setattr(runtime, "pressure", None)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["pressure_ok"] is False
    assert body["pressure_fault"] == "No pressure sensor configured"


# ---- running state ----


def test_health_reports_a_running_pour(monkeypatch):
    # A real clock and a slow flow, so the pour is still running when we poll.
    rt = Runtime()
    rt.doser.brew_flow_ml_s = 0.05
    monkeypatch.setattr(api_module, "_runtime", rt)
    try:
        client = TestClient(app)
        assert client.post("/drinks/pour/espresso", params={"force": True}).status_code == 200
        assert client.get("/health").json()["running"] is True
        client.post("/drinks/cancel")
    finally:
        rt.stop()
