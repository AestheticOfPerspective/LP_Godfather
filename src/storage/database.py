from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class ConversationEntry:
    role: str
    content: str
    platform: str
    persona: str
    timestamp: float


@dataclass
class UserRecord:
    user_id: str
    platform: str
    username: Optional[str]
    first_seen: float
    total_messages: int
    persona_affinity: Dict[str, float]


class Database:
    def __init__(self, db_path: str = "data/godfather.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    username TEXT,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    total_messages INTEGER DEFAULT 0,
                    persona_affinity TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    persona TEXT NOT NULL DEFAULT 'default',
                    model TEXT,
                    tokens INTEGER DEFAULT 0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS persona_state (
                    key TEXT PRIMARY KEY,
                    current_persona TEXT NOT NULL,
                    previous_persona TEXT,
                    affinity TEXT DEFAULT '{}',
                    last_transition REAL,
                    transition_count INTEGER DEFAULT 0,
                    messages_since_transition INTEGER DEFAULT 0,
                    locked INTEGER DEFAULT 0,
                    locked_by TEXT
                );

                CREATE TABLE IF NOT EXISTS ollama_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    latency_ms REAL,
                    success INTEGER DEFAULT 1,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, key)
                );

                CREATE TABLE IF NOT EXISTS allowed_groups (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    added_by TEXT DEFAULT '',
                    added_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    last_call REAL NOT NULL,
                    PRIMARY KEY (user_id, command)
                );

                CREATE INDEX IF NOT EXISTS idx_conv_user
                    ON conversations(user_id, platform);
                CREATE INDEX IF NOT EXISTS idx_conv_chat
                    ON conversations(chat_id, platform);
                CREATE INDEX IF NOT EXISTS idx_conv_timestamp
                    ON conversations(timestamp);
                CREATE INDEX IF NOT EXISTS idx_ollama_timestamp
                    ON ollama_stats(timestamp);
                CREATE INDEX IF NOT EXISTS idx_memories_user
                    ON user_memories(user_id);
            """)

    def upsert_user(self, user_id: str, platform: str, username: Optional[str] = None):
        with self._get_conn() as conn:
            now = time.time()
            conn.execute("""
                INSERT INTO users (id, platform, username, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    total_messages = total_messages + 1,
                    username = COALESCE(excluded.username, username)
            """, (user_id, platform, username, now, now))

    def save_conversation(self, user_id: str, platform: str, chat_id: str,
                          role: str, content: str, persona: str = "default",
                          model: Optional[str] = None, tokens: int = 0):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO conversations
                    (user_id, platform, chat_id, role, content, persona, model, tokens, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, platform, chat_id, role, content, persona, model, tokens, time.time()))

    def get_recent_conversations(self, user_id: str, platform: str,
                                  limit: int = 20) -> List[ConversationEntry]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT role, content, platform, persona, timestamp
                FROM conversations
                WHERE user_id = ? AND platform = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, platform, limit)).fetchall()
        return [
            ConversationEntry(
                role=r["role"], content=r["content"],
                platform=r["platform"], persona=r["persona"],
                timestamp=r["timestamp"]
            )
            for r in reversed(rows)
        ]

    def save_persona_state(self, key: str, current: str, previous: Optional[str],
                            affinity: Dict[str, float], last_transition: float,
                            transition_count: int, messages_since: int,
                            locked: bool = False, locked_by: Optional[str] = None):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO persona_state
                    (key, current_persona, previous_persona, affinity,
                     last_transition, transition_count, messages_since_transition,
                     locked, locked_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    current_persona = excluded.current_persona,
                    previous_persona = excluded.previous_persona,
                    affinity = excluded.affinity,
                    last_transition = excluded.last_transition,
                    transition_count = excluded.transition_count,
                    messages_since_transition = excluded.messages_since_transition,
                    locked = excluded.locked,
                    locked_by = excluded.locked_by
            """, (key, current, previous, json.dumps(affinity),
                  last_transition, transition_count, messages_since,
                  1 if locked else 0, locked_by))

    def load_persona_state(self, key: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM persona_state WHERE key = ?
            """, (key,)).fetchone()
        if not row:
            return None
        return {
            "current": row["current_persona"],
            "previous": row["previous_persona"],
            "affinity": json.loads(row["affinity"]),
            "last_transition": row["last_transition"],
            "transition_count": row["transition_count"],
            "messages_since": row["messages_since_transition"],
            "locked": bool(row["locked"]),
            "locked_by": row["locked_by"],
        }

    def log_ollama_call(self, url: str, model: str, tokens: int,
                         latency_ms: float, success: bool):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO ollama_stats (url, model, tokens, latency_ms, success, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url, model, tokens, latency_ms, 1 if success else 0, time.time()))

    def get_user_stats(self, user_id: str, platform: str) -> dict:
        with self._get_conn() as conn:
            user = conn.execute("""
                SELECT * FROM users WHERE id = ?
            """, (user_id,)).fetchone()

            counts = conn.execute("""
                SELECT
                    COUNT(*) as total_msgs,
                    COUNT(DISTINCT persona) as personas_used,
                    SUM(tokens) as total_tokens
                FROM conversations
                WHERE user_id = ? AND platform = ?
            """, (user_id, platform)).fetchone()

        return {
            "total_messages": counts["total_msgs"] if counts else 0,
            "personas_used": counts["personas_used"] if counts else 0,
            "total_tokens": counts["total_tokens"] or 0,
            "last_seen": user["last_seen"] if user else None,
        }

    def load_recent_conversations_dict(self, user_id: str, platform: str,
                                        limit: int = 20) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT role, content
                FROM conversations
                WHERE user_id = ? AND platform = ? AND role IN ('user', 'assistant')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, platform, limit)).fetchall()
        result = []
        for r in reversed(rows):
            result.append({"role": r["role"], "content": r["content"]})
        return result

    def get_user_preferences(self, user_id: str) -> dict:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT persona_affinity FROM users WHERE id = ?
            """, (user_id,)).fetchone()
        if row and row["persona_affinity"]:
            try:
                return json.loads(row["persona_affinity"])
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    def save_memory(self, user_id: str, key: str, value: str,
                     category: str = "general") -> None:
        now = time.time()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO user_memories (user_id, key, value, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = excluded.updated_at
            """, (user_id, key, value, category, now, now))

    def get_memory(self, user_id: str, key: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT value FROM user_memories
                WHERE user_id = ? AND key = ?
            """, (user_id, key)).fetchone()
        return row["value"] if row else None

    def get_all_memories(self, user_id: str,
                          category: Optional[str] = None) -> list[dict]:
        with self._get_conn() as conn:
            if category:
                rows = conn.execute("""
                    SELECT key, value, category, updated_at
                    FROM user_memories
                    WHERE user_id = ? AND category = ?
                    ORDER BY updated_at DESC
                """, (user_id, category)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT key, value, category, updated_at
                    FROM user_memories
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, user_id: str, key: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("""
                DELETE FROM user_memories WHERE user_id = ? AND key = ?
            """, (user_id, key))
            return cur.rowcount > 0

    def is_group_allowed(self, chat_id: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM allowed_groups WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row is not None

    def allow_group(self, chat_id: str, title: str = "", added_by: str = ""):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO allowed_groups (chat_id, title, added_by, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    added_at = excluded.added_at
            """, (chat_id, title, added_by, time.time()))

    def remove_group(self, chat_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM allowed_groups WHERE chat_id = ?", (chat_id,))
            return cur.rowcount > 0

    def list_allowed_groups(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT chat_id, title, added_by, added_at FROM allowed_groups ORDER BY added_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def check_rate_limit(self, user_id: str, command: str,
                          cooldown_seconds: int = 2) -> tuple[bool, float]:
        now = time.time()
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT last_call FROM rate_limits
                WHERE user_id = ? AND command = ?
            """, (user_id, command)).fetchone()
            if row:
                elapsed = now - row["last_call"]
                if elapsed < cooldown_seconds:
                    return False, cooldown_seconds - elapsed
                conn.execute("""
                    UPDATE rate_limits SET last_call = ? WHERE user_id = ? AND command = ?
                """, (now, user_id, command))
            else:
                conn.execute("""
                    INSERT INTO rate_limits (user_id, command, last_call)
                    VALUES (?, ?, ?)
                """, (user_id, command, now))
            conn.commit()
        return True, 0.0

    def get_global_stats(self) -> dict:
        with self._get_conn() as conn:
            msgs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            users = conn.execute("SELECT COUNT(DISTINCT id) FROM users").fetchone()[0]
            tokens = conn.execute("SELECT COALESCE(SUM(tokens), 0) FROM conversations").fetchone()[0]
            calls = conn.execute("SELECT COUNT(*) FROM ollama_stats").fetchone()[0]
            avg_latency = conn.execute(
                "SELECT COALESCE(AVG(latency_ms), 0) FROM ollama_stats WHERE success = 1"
            ).fetchone()[0]
        return {
            "total_messages": msgs,
            "total_users": users,
            "total_tokens": tokens,
            "ollama_calls": calls,
            "avg_latency_ms": round(avg_latency, 1),
        }
