import sqlite3
from pathlib import Path

from scripts.import_legacy_db import import_database
from src.storage.database import Database


def test_legacy_import_is_idempotent(tmp_path: Path):
    source = tmp_path / "legacy.db"
    target = tmp_path / "v4.db"
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            CREATE TABLE user_facts (
                id INTEGER PRIMARY KEY, user_id TEXT, fact_text TEXT, created_at TEXT
            );
            CREATE TABLE conversation_history (
                id INTEGER PRIMARY KEY, user_id TEXT, role TEXT, content TEXT, created_at TEXT
            );
            INSERT INTO user_facts VALUES (1, '42', 'likes synthwave', '2026-06-01 12:00:00');
            INSERT INTO conversation_history VALUES (1, '42', 'user', 'yo', '2026-06-01 12:01:00');
        """)

    Database(str(target))
    first = import_database(source, target)
    second = import_database(source, target)

    assert first == {"conversation_history": 1, "user_facts": 1}
    assert second == {"conversation_history": 0, "user_facts": 0}
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM legacy_records").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user_memories").fetchone()[0] == 1

