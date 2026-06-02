"""
utils/storage.py — SQLite-basierte Datenspeicherung
Kein Server nötig, alles lokal, leicht zu backuppen.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str | None = None):
        if path is None:
            try:
                from config import DB_PATH as configured_path
                path = configured_path
            except Exception:
                path = "data/godfather.db"
        if not path:
            path = "data/godfather.db"
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

            CREATE TABLE IF NOT EXISTS trusted_users (
                user_id    TEXT PRIMARY KEY,
                username   TEXT NOT NULL,
                role       TEXT NOT NULL DEFAULT 'trusted_choom',
                added_by   TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS moderation_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT NOT NULL,
                target_user TEXT NOT NULL,
                actor_user  TEXT NOT NULL,
                reason      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS song_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,
                artist      TEXT NOT NULL,
                title       TEXT NOT NULL,
                link        TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS clip_submissions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,
                chat_id     TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                username    TEXT,
                text        TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stream_recaps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,
                actor       TEXT NOT NULL,
                body        TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_facts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                fact_text   TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS knowledge_base (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                content     TEXT NOT NULL,
                source      TEXT DEFAULT 'manual',
                added_by    TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS chat_contexts (
                chat_id     TEXT PRIMARY KEY,
                chat_type   TEXT NOT NULL,
                title       TEXT,
                purpose     TEXT,
                needs       TEXT,
                updated_by  TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback_events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                source            TEXT NOT NULL,
                chat_id           TEXT NOT NULL,
                chat_type         TEXT,
                chat_title        TEXT,
                user_id           TEXT,
                username          TEXT,
                target_message_id TEXT,
                event_kind        TEXT NOT NULL,
                payload           TEXT NOT NULL,
                polarity          TEXT NOT NULL DEFAULT 'neutral',
                confidence        REAL NOT NULL DEFAULT 0.0,
                created_at        TEXT DEFAULT (datetime('now'))
            );
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


    # ── Trusted Users (Twitch Choombata) ─────────────────────────────────────

    def add_trusted(self, user_id: str, username: str, added_by: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO trusted_users (user_id, username, role, added_by) VALUES (?, ?, 'trusted_choom', ?)",
            (user_id, username, added_by)
        )
        self.conn.commit()

    def remove_trusted(self, user_id: str) -> None:
        self.conn.execute("DELETE FROM trusted_users WHERE user_id=?", (user_id,))
        self.conn.commit()

    def is_trusted(self, user_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM trusted_users WHERE user_id=?", (user_id,))
        return cur.fetchone() is not None

    def list_trusted(self) -> list[tuple]:
        cur = self.conn.execute("SELECT username, role, created_at FROM trusted_users ORDER BY created_at")
        return cur.fetchall()

    # ── Moderation Events (Twitch) ────────────────────────────────────────────

    def add_mod_event(self, action: str, target: str, actor: str, reason: str = "") -> None:
        self.conn.execute(
            "INSERT INTO moderation_events (action, target_user, actor_user, reason) VALUES (?, ?, ?, ?)",
            (action, target, actor, reason)
        )
        self.conn.commit()

    # ── Song Events ───────────────────────────────────────────────────────────

    def add_song_event(self, source: str, artist: str, title: str, link: str = "") -> None:
        self.conn.execute(
            "INSERT INTO song_events (source, artist, title, link) VALUES (?, ?, ?, ?)",
            (source, artist, title, link)
        )
        self.conn.commit()

    def last_song(self) -> tuple | None:
        cur = self.conn.execute(
            "SELECT artist, title, link, created_at FROM song_events ORDER BY id DESC LIMIT 1"
        )
        return cur.fetchone()

    # ── Stream Utility ───────────────────────────────────────────────────────

    def add_clip_submission(
        self,
        source: str,
        chat_id: str,
        user_id: str,
        username: str,
        text: str,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO clip_submissions (source, chat_id, user_id, username, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source, chat_id, user_id, username, text),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def recent_clip_submissions(self, limit: int = 5) -> list[tuple]:
        cur = self.conn.execute(
            """
            SELECT source, username, text, created_at
            FROM clip_submissions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()

    def add_stream_recap(self, source: str, actor: str, body: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO stream_recaps (source, actor, body) VALUES (?, ?, ?)",
            (source, actor, body),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def latest_stream_recap(self) -> tuple | None:
        cur = self.conn.execute(
            """
            SELECT source, actor, body, created_at
            FROM stream_recaps
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return cur.fetchone()

    # ── User Facts ──────────────────────────────────────────────────────────────

    def add_user_fact(self, user_id: str, fact_text: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO user_facts (user_id, fact_text) VALUES (?, ?)",
            (user_id, fact_text),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def get_user_facts(self, user_id: str) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT id, fact_text, created_at FROM user_facts WHERE user_id=? ORDER BY id DESC",
            (user_id,),
        )
        return cur.fetchall()

    def search_user_facts(self, user_id: str, query: str) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT id, fact_text, created_at FROM user_facts WHERE user_id=? AND fact_text LIKE ? ORDER BY id DESC",
            (user_id, f"%{query}%"),
        )
        return cur.fetchall()

    def delete_user_fact(self, fact_id: int, user_id: str) -> bool:
        cur = self.conn.execute(
            "DELETE FROM user_facts WHERE id=? AND user_id=?",
            (fact_id, user_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def count_user_facts(self, user_id: str) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM user_facts WHERE user_id=?", (user_id,)
        )
        return cur.fetchone()[0]

    # ── Knowledge Base ──────────────────────────────────────────────────────────

    def add_knowledge(self, topic: str, content: str, source: str, added_by: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO knowledge_base (topic, content, source, added_by) VALUES (?, ?, ?, ?)",
            (topic, content, source, added_by),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def search_knowledge(self, query: str) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT id, topic, content, source, created_at FROM knowledge_base WHERE topic LIKE ? OR content LIKE ? ORDER BY id DESC LIMIT 10",
            (f"%{query}%", f"%{query}%"),
        )
        return cur.fetchall()

    def get_knowledge_by_topic(self, topic: str) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT id, topic, content, source, created_at FROM knowledge_base WHERE topic=? ORDER BY id DESC",
            (topic,),
        )
        return cur.fetchall()

    def list_knowledge_topics(self) -> list[str]:
        cur = self.conn.execute(
            "SELECT DISTINCT topic FROM knowledge_base ORDER BY topic"
        )
        return [row[0] for row in cur.fetchall()]

    def delete_knowledge(self, knowledge_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM knowledge_base WHERE id=?", (knowledge_id,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ── Chat Contexts ─────────────────────────────────────────────────────────

    def upsert_chat_context(
        self,
        chat_id: str,
        chat_type: str,
        title: str,
        purpose: str,
        needs: str,
        updated_by: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO chat_contexts (chat_id, chat_type, title, purpose, needs, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type=excluded.chat_type,
                title=excluded.title,
                purpose=excluded.purpose,
                needs=excluded.needs,
                updated_by=excluded.updated_by,
                updated_at=datetime('now')
            """,
            (chat_id, chat_type, title, purpose, needs, updated_by),
        )
        self.conn.commit()

    def get_chat_context(self, chat_id: str) -> tuple | None:
        cur = self.conn.execute(
            """
            SELECT chat_id, chat_type, title, purpose, needs, updated_by, updated_at
            FROM chat_contexts
            WHERE chat_id=?
            """,
            (chat_id,),
        )
        return cur.fetchone()

    # ── Feedback Events ───────────────────────────────────────────────────────

    def add_feedback_event(
        self,
        source: str,
        chat_id: str,
        chat_type: str,
        chat_title: str,
        user_id: str,
        username: str,
        target_message_id: str,
        event_kind: str,
        payload: str,
        polarity: str = "neutral",
        confidence: float = 0.0,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO feedback_events (
                source, chat_id, chat_type, chat_title, user_id, username,
                target_message_id, event_kind, payload, polarity, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                chat_id,
                chat_type,
                chat_title,
                user_id,
                username,
                target_message_id,
                event_kind,
                payload,
                polarity,
                confidence,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def recent_feedback_events(self, limit: int = 20) -> list[tuple]:
        cur = self.conn.execute(
            """
            SELECT id, source, chat_title, username, event_kind, payload, polarity, confidence, created_at
            FROM feedback_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()

    def feedback_summary(self, chat_id: str | None = None) -> dict:
        where = "WHERE chat_id=?" if chat_id else ""
        params = (chat_id,) if chat_id else ()
        cur = self.conn.execute(
            f"""
            SELECT polarity, COUNT(*)
            FROM feedback_events
            {where}
            GROUP BY polarity
            """,
            params,
        )
        return dict(cur.fetchall())


# Singleton
db = Database()
