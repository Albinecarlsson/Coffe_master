from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from espresso_mod import api as api_module
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


def _poll_shot(client, states, timeout=2.0):
    body = client.get("/shot/status").json()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get("/shot/status").json()
        if body["state"] in states:
            return body
        time.sleep(0.01)
    return body


# ---- UI ----


def test_ui_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Espresso Mod" in response.text


# ---- State & control ----


def test_state_reports_defaults(client):
    body = client.get("/state").json()

    assert body["control_enabled"] is False
    assert body["setpoint_c"] == 93.0
    assert body["temp_ok"] is True
    assert isinstance(body["temp_c"], float)
    assert body["valve_open"] == 0.0


def test_setpoint_updates_state(client):
    response = client.post("/control/setpoint", json={"setpoint_c": 96.5})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "setpoint_c": 96.5}
    assert client.get("/state").json()["setpoint_c"] == 96.5


@pytest.mark.parametrize("bad_setpoint", [-1, 131, 200])
def test_setpoint_out_of_range_is_rejected(client, bad_setpoint):
    response = client.post("/control/setpoint", json={"setpoint_c": bad_setpoint})

    assert response.status_code == 422


def test_enable_and_disable_control(client):
    enabled = client.post("/control/enable", json={"enabled": True})
    assert enabled.json() == {"ok": True, "enabled": True}
    assert client.get("/state").json()["control_enabled"] is True

    disabled = client.post("/control/enable", json={"enabled": False})
    assert disabled.json() == {"ok": True, "enabled": False}
    assert client.get("/state").json()["control_enabled"] is False


def test_valve_command_updates_state(client):
    response = client.post("/valve", json={"open_0_to_1": 0.5})

    assert response.status_code == 200
    assert client.get("/state").json()["valve_open"] == pytest.approx(0.5)


def test_valve_out_of_range_is_rejected(client):
    assert client.post("/valve", json={"open_0_to_1": 2.0}).status_code == 422


# ---- Telemetry ----


def test_telemetry_returns_sampled_points(client):
    # The sampler runs on the real clock at 10 Hz, so give it a moment.
    time.sleep(0.4)

    body = client.get("/telemetry", params={"seconds": 60}).json()

    assert len(body["points"]) >= 1
    point = body["points"][0]
    assert point.keys() >= {
        "ts",
        "temp_c",
        "temp_ok",
        "heater_power",
        "valve_open",
        "setpoint_c",
        "control_enabled",
    }


def test_telemetry_window_is_validated(client):
    assert client.get("/telemetry", params={"seconds": 0}).status_code == 422


# ---- Shots ----


def test_shot_profiles_lists_known_profiles(client):
    body = client.get("/shot/profiles").json()

    assert "classic_espresso" in body["profiles"]
    assert "lungo" in body["profiles"]


def test_shot_status_starts_idle(client):
    assert client.get("/shot/status").json()["state"] == "idle"


def test_unknown_shot_profile_returns_404(client):
    response = client.post("/shot/start/not_a_profile")

    assert response.status_code == 404


def test_shot_runs_to_completion_and_closes_valve(client):
    started = client.post("/shot/start/classic_espresso")
    assert started.status_code == 200
    assert started.json() == {"ok": True, "started": "classic_espresso"}

    status = _poll_shot(client, ("done", "error", "canceled"))

    assert status["state"] == "done"
    assert status["profile"] == "classic_espresso"
    assert status["total_elapsed_s"] == pytest.approx(28.0, abs=0.1)
    assert client.get("/state").json()["valve_open"] == 0.0


def test_shot_can_be_canceled(client):
    client.post("/shot/start/classic_espresso")

    assert client.post("/shot/cancel").json() == {"ok": True}

    status = _poll_shot(client, ("canceled", "done", "error"))
    assert status["state"] in ("canceled", "done")


def test_shot_start_while_running_returns_409(monkeypatch):
    # Uses the system clock so the shot is still running when we start again.
    rt = Runtime()
    monkeypatch.setattr(api_module, "_runtime", rt)
    try:
        client = TestClient(app)
        assert client.post("/shot/start/classic_espresso").status_code == 200
        assert client.post("/shot/start/classic_espresso").status_code == 409
        client.post("/shot/cancel")
    finally:
        rt.stop()


# ---- Runtime wiring ----


def test_get_runtime_is_a_lazy_singleton(monkeypatch):
    monkeypatch.setattr(api_module, "_runtime", None)

    first = api_module.get_runtime()
    try:
        assert api_module.get_runtime() is first
    finally:
        first.stop()
