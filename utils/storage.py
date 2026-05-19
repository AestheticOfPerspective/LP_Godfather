"""
utils/storage.py — SQLite-basierte Datenspeicherung
Kein Server nötig, alles lokal, leicht zu backuppen.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

from config import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str = DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init_tables()
        logger.info(f"Datenbank geladen: {path}")

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS warns (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT NOT NULL,
                user_id   TEXT NOT NULL,
                reason    TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stats (
                key   TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            );

            INSERT OR IGNORE INTO stats (key, value) VALUES
                ('messages', 0),
                ('joins', 0),
                ('warns', 0),
                ('ai_requests', 0);
        """)
        self.conn.commit()

    # ── Warns ─────────────────────────────────────────────────────────────────

    def add_warn(self, chat_id: str, user_id: str, reason: str) -> int:
        """Fügt eine Verwarnung hinzu und gibt die aktuelle Anzahl zurück."""
        self.conn.execute(
            "INSERT INTO warns (chat_id, user_id, reason) VALUES (?, ?, ?)",
            (chat_id, user_id, reason)
        )
        self.conn.commit()
        self.increment_stat("warns")
        return self.count_warns(chat_id, user_id)

    def count_warns(self, chat_id: str, user_id: str) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM warns WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        return cur.fetchone()[0]

    def get_warns(self, chat_id: str, user_id: str) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT reason, timestamp FROM warns WHERE chat_id=? AND user_id=? ORDER BY id",
            (chat_id, user_id)
        )
        return cur.fetchall()

    def clear_warns(self, chat_id: str, user_id: str) -> None:
        self.conn.execute(
            "DELETE FROM warns WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        self.conn.commit()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def increment_stat(self, key: str, amount: int = 1) -> None:
        self.conn.execute(
            "UPDATE stats SET value = value + ? WHERE key = ?",
            (amount, key)
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        cur = self.conn.execute("SELECT key, value FROM stats")
        return dict(cur.fetchall())


# Singleton
db = Database()
