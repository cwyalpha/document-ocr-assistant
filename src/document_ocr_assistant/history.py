from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .settings import data_directory


@dataclass(slots=True)
class HistoryEntry:
    id: int
    created_at: str
    text: str
    image_path: str | None


class HistoryStore:
    def __init__(self, path: Path | None = None, limit: int = 100) -> None:
        self.path = path or data_directory() / "history.sqlite3"
        self.limit = max(1, limit)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS screenshot_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    text TEXT NOT NULL,
                    image_path TEXT
                )
                """
            )

    def add(self, text: str, image_path: str | None = None) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO screenshot_history(created_at, text, image_path) VALUES (?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), text, image_path),
            )
            connection.execute(
                """
                DELETE FROM screenshot_history
                WHERE id NOT IN (
                    SELECT id FROM screenshot_history ORDER BY id DESC LIMIT ?
                )
                """,
                (self.limit,),
            )
            return int(cursor.lastrowid)

    def list(self) -> list[HistoryEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, created_at, text, image_path FROM screenshot_history ORDER BY id DESC"
            ).fetchall()
        return [HistoryEntry(row["id"], row["created_at"], row["text"], row["image_path"]) for row in rows]

    def delete(self, entry_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM screenshot_history WHERE id = ?", (entry_id,))

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM screenshot_history")

