"""Persisted record of every shot and pour.

One SQLite file, one row per finished pour. Connections are opened per write
rather than shared: the doser and the shot runner finish on different threads, and
a per-write connection keeps the sqlite3 handle on the thread that uses it.

Writing history must never break a pour, so callers invoke this from a guarded
callback — see ``ShotRunner.on_finish`` and ``Doser.on_finish``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from espresso_mod.domain.models import HistoryEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pours (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at  REAL    NOT NULL,
    kind         TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    target_ml    REAL,
    delivered_ml REAL,
    elapsed_s    REAL    NOT NULL,
    message      TEXT
)
"""

# Column order must match HistoryEntry's positional constructor below.
_COLUMNS = "id, finished_at, kind, name, state, target_ml, delivered_ml, elapsed_s, message"


class ShotHistory:
    """Append-only log of shots and pours, backed by SQLite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self,
        *,
        kind: str,
        name: str,
        state: str,
        elapsed_s: float,
        target_ml: float | None = None,
        delivered_ml: float | None = None,
        message: str | None = None,
        finished_at: float | None = None,
    ) -> None:
        """Append one finished pour. Creates the database and directory lazily."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(_SCHEMA)
            conn.execute(
                "INSERT INTO pours"
                " (finished_at, kind, name, state, target_ml, delivered_ml, elapsed_s, message)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time() if finished_at is None else finished_at,
                    kind,
                    name,
                    state,
                    target_ml,
                    delivered_ml,
                    elapsed_s,
                    message,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def recent(self, limit: int = 20) -> list[HistoryEntry]:
        """Newest first. Empty if nothing has ever been recorded."""
        if limit <= 0 or not self.path.exists():
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM pours ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()
        return [self._to_entry(row) for row in rows]

    @staticmethod
    def _to_entry(row: tuple[Any, ...]) -> HistoryEntry:
        return HistoryEntry(
            id=row[0],
            finished_at=row[1],
            kind=row[2],
            name=row[3],
            state=row[4],
            target_ml=row[5],
            delivered_ml=row[6],
            elapsed_s=row[7],
            message=row[8],
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)
