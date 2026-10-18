from __future__ import annotations

import sqlite3

import pytest

from espresso_mod.services.history import ShotHistory


def _history(tmp_path) -> ShotHistory:
    # a nested path, to prove the parent directory is created on demand
    return ShotHistory(tmp_path / "nested" / "history.db")


def test_recent_is_empty_before_anything_is_recorded(tmp_path):
    history = _history(tmp_path)

    assert history.recent() == []
    # reading must not create the database
    assert not history.path.exists()


def test_record_persists_a_pour(tmp_path):
    history = _history(tmp_path)

    history.record(
        kind="drink",
        name="espresso",
        state="done",
        elapsed_s=27.3,
        target_ml=30.0,
        delivered_ml=30.0,
        message="Poured 30 ml",
        finished_at=1234.5,
    )

    [entry] = history.recent()
    assert entry.kind == "drink"
    assert entry.name == "espresso"
    assert entry.state == "done"
    assert entry.target_ml == 30.0
    assert entry.delivered_ml == 30.0
    assert entry.elapsed_s == pytest.approx(27.3)
    assert entry.message == "Poured 30 ml"
    assert entry.finished_at == 1234.5
    assert history.path.exists()


def test_entries_come_back_newest_first(tmp_path):
    history = _history(tmp_path)
    for name in ("ristretto", "espresso", "lungo"):
        history.record(kind="drink", name=name, state="done", elapsed_s=1.0)

    assert [e.name for e in history.recent()] == ["lungo", "espresso", "ristretto"]


def test_record_persists_the_peak_pressure(tmp_path):
    history = _history(tmp_path)

    history.record(kind="drink", name="espresso", state="done", elapsed_s=27.0, peak_bar=9.4)

    [entry] = history.recent()
    assert entry.peak_bar == pytest.approx(9.4)


def test_an_old_database_gains_the_pressure_column(tmp_path):
    """The user's existing history predates pressure logging."""
    path = tmp_path / "old" / "history.db"
    path.parent.mkdir()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE pours ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " finished_at REAL NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,"
        " state TEXT NOT NULL, target_ml REAL, delivered_ml REAL,"
        " elapsed_s REAL NOT NULL, message TEXT)"
    )
    conn.execute(
        "INSERT INTO pours (finished_at, kind, name, state, elapsed_s)"
        " VALUES (1.0, 'drink', 'espresso', 'done', 27.0)"
    )
    conn.commit()
    conn.close()

    history = ShotHistory(path)

    [entry] = history.recent()
    assert entry.name == "espresso"
    assert entry.peak_bar is None

    history.record(kind="drink", name="lungo", state="done", elapsed_s=50.0, peak_bar=8.1)
    assert history.recent(1)[0].peak_bar == pytest.approx(8.1)


def test_limit_caps_the_result(tmp_path):
    history = _history(tmp_path)
    for index in range(5):
        history.record(kind="shot", name=f"s{index}", state="done", elapsed_s=1.0)

    assert [e.name for e in history.recent(2)] == ["s4", "s3"]
    assert history.recent(0) == []
    assert history.recent(-1) == []


def test_a_shot_entry_has_no_volume(tmp_path):
    history = _history(tmp_path)

    history.record(kind="shot", name="classic_espresso", state="done", elapsed_s=28.0)

    [entry] = history.recent()
    assert entry.target_ml is None
    assert entry.delivered_ml is None


def test_records_survive_a_new_instance(tmp_path):
    path = tmp_path / "history.db"
    ShotHistory(path).record(kind="drink", name="espresso", state="done", elapsed_s=1.0)

    assert len(ShotHistory(path).recent()) == 1


def test_finished_at_defaults_to_now(tmp_path):
    history = ShotHistory(tmp_path / "history.db")

    history.record(kind="drink", name="espresso", state="done", elapsed_s=1.0)

    [entry] = history.recent()
    assert entry.finished_at > 0.0
