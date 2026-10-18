from __future__ import annotations

import pytest

from espresso_mod.config import settings


class FakeClock:
    """Deterministic clock whose ``sleep`` advances virtual time instantly.

    Services injected with this clock run their time-based logic at full
    speed, so a 28-second shot profile completes in microseconds.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self._t += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh :class:`FakeClock` for each test."""
    return FakeClock()


@pytest.fixture(autouse=True)
def _isolated_history_db(tmp_path, monkeypatch):
    """Keep each test's shot history out of the repo and out of every other test."""
    monkeypatch.setattr(settings, "history_db_path", str(tmp_path / "history.db"))
