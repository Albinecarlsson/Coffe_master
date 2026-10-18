from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from espresso_mod import api as api_module
from espresso_mod.domain.drinks import DRINKS
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


@pytest.fixture
def hot_runtime(monkeypatch, fake_clock):
    """A runtime whose simulated boiler starts already at brew temperature."""
    monkeypatch.setattr(api_module.settings, "sim_initial_water_c", 93.0)
    rt = Runtime(clock=fake_clock)
    monkeypatch.setattr(api_module, "_runtime", rt)
    yield rt
    rt.stop()


@pytest.fixture
def hot_client(hot_runtime):
    return TestClient(app)


def _poll_pour(client, states, timeout=2.0):
    body = client.get("/kiosk/status").json()["pour"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get("/kiosk/status").json()["pour"]
        if body["state"] in states:
            return body
        time.sleep(0.01)
    return body


# ---- UI ----


def test_kiosk_page_is_served(client):
    response = client.get("/kiosk")

    assert response.status_code == 200
    assert "Choose your coffee" in response.text


# ---- drinks ----


def test_drinks_lists_the_whole_catalogue(client):
    body = client.get("/drinks").json()

    assert {d["key"] for d in body["drinks"]} == set(DRINKS)
    assert body["brew_flow_ml_s"] > 0.0

    espresso = next(d for d in body["drinks"] if d["key"] == "espresso")
    assert espresso["name"] == "Espresso"
    assert espresso["water_ml"] == DRINKS["espresso"].water_ml
    assert espresso["setpoint_c"] == DRINKS["espresso"].setpoint_c


def test_kiosk_status_reports_readiness_and_idle_pour(hot_client):
    body = hot_client.get("/kiosk/status").json()

    assert body["temp_ok"] is True
    assert body["temp_fault"] is None
    assert body["temp_c"] == pytest.approx(93.0, abs=1.0)
    assert body["ready"] is True
    assert body["pour"]["state"] == "idle"
    assert body["pour"]["delivered_ml"] == 0.0


def test_kiosk_status_is_not_ready_on_a_cold_boiler(client):
    body = client.get("/kiosk/status").json()

    assert body["temp_ok"] is True
    assert body["ready"] is False


# ---- pouring ----


def test_pouring_a_drink_delivers_its_volume_and_closes_the_valve(hot_client):
    assert hot_client.get("/kiosk/status").json()["ready"] is True

    started = hot_client.post("/drinks/pour/espresso")

    assert started.status_code == 200
    assert started.json() == {"ok": True, "pouring": "espresso", "target_ml": 30.0}

    status = _poll_pour(hot_client, ("done", "error", "canceled"))
    assert status["state"] == "done"
    assert status["drink"] == "espresso"
    assert status["delivered_ml"] == pytest.approx(30.0)
    assert hot_client.get("/state").json()["valve_open"] == 0.0


def test_a_drink_sets_its_own_boiler_temperature(client, runtime):
    client.post("/drinks/pour/espresso", params={"force": True})

    assert runtime.control.setpoint_c == pytest.approx(DRINKS["espresso"].setpoint_c)


def test_unknown_drink_returns_404(client):
    response = client.post("/drinks/pour/unicorn")

    assert response.status_code == 404
    assert "unicorn" in response.json()["detail"]


def test_pouring_a_cold_boiler_is_refused_but_aims_the_setpoint(client, runtime):
    response = client.post("/drinks/pour/lungo")

    assert response.status_code == 409
    assert "not at" in response.json()["detail"]
    # tapping a drink still starts heating towards it
    assert runtime.control.setpoint_c == pytest.approx(DRINKS["lungo"].setpoint_c)
    assert client.get("/kiosk/status").json()["pour"]["state"] == "idle"


def test_force_pours_on_a_cold_boiler(client):
    started = client.post("/drinks/pour/espresso", params={"force": True})

    assert started.status_code == 200
    assert _poll_pour(client, ("done", "error"))["state"] == "done"


def test_a_pour_can_be_canceled(client):
    client.post("/drinks/pour/espresso", params={"force": True})

    assert client.post("/drinks/cancel").json() == {"ok": True}

    assert _poll_pour(client, ("canceled", "done"))["state"] in ("canceled", "done")


def test_pour_while_pouring_returns_409(monkeypatch):
    # Real clock and a slow flow, so the first pour is still running.
    rt = Runtime()
    rt.doser.brew_flow_ml_s = 0.05
    monkeypatch.setattr(api_module, "_runtime", rt)
    try:
        client = TestClient(app)
        assert client.post("/drinks/pour/espresso", params={"force": True}).status_code == 200
        assert client.post("/drinks/pour/lungo", params={"force": True}).status_code == 409
        client.post("/drinks/cancel")
    finally:
        rt.stop()


def test_shot_cannot_start_while_a_drink_is_pouring(monkeypatch):
    rt = Runtime()
    rt.doser.brew_flow_ml_s = 0.05
    monkeypatch.setattr(api_module, "_runtime", rt)
    try:
        client = TestClient(app)
        assert client.post("/drinks/pour/espresso", params={"force": True}).status_code == 200
        assert client.post("/shot/start/classic_espresso").status_code == 409
        client.post("/drinks/cancel")
    finally:
        rt.stop()


def test_drink_cannot_start_while_a_shot_is_running(monkeypatch):
    # classic_espresso runs for 28 s on the real clock, so it is still running.
    rt = Runtime()
    monkeypatch.setattr(api_module, "_runtime", rt)
    try:
        client = TestClient(app)
        assert client.post("/shot/start/classic_espresso").status_code == 200

        response = client.post("/drinks/pour/espresso", params={"force": True})

        assert response.status_code == 409
        assert response.json()["detail"] == "A shot is already running"
        client.post("/shot/cancel")
    finally:
        rt.stop()
