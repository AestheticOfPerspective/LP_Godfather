from __future__ import annotations
import time

import pytest

from src.storage.database import Database


class TestDatabase:
    def test_init_creates_tables(self, temp_db_path: str):
        db = Database(temp_db_path)
        with db._get_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        names = [r[0] for r in tables]
        assert "users" in names
        assert "conversations" in names
        assert "persona_state" in names
        assert "ollama_stats" in names
        assert "user_memories" in names
        assert "allowed_groups" in names
        assert "rate_limits" in names

    def test_upsert_user(self, database: Database):
        database.upsert_user("user_1", "telegram", "testuser")
        with database._get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", ("user_1",)).fetchone()
        assert row["username"] == "testuser"
        assert row["platform"] == "telegram"

    def test_upsert_user_increments_count(self, database: Database):
        database.upsert_user("user_1", "telegram", "testuser")
        database.upsert_user("user_1", "telegram", None)
        with database._get_conn() as conn:
            row = conn.execute("SELECT total_messages FROM users WHERE id = ?", ("user_1",)).fetchone()
        assert row["total_messages"] == 1

    def test_save_and_get_conversations(self, database: Database):
        database.upsert_user("user_1", "telegram", "testuser")
        database.save_conversation("user_1", "telegram", "chat_1", "user", "Hello", "godfather")
        database.save_conversation("user_1", "telegram", "chat_1", "assistant", "Hi there!", "godfather")

        entries = database.get_recent_conversations("user_1", "telegram", limit=10)
        assert len(entries) == 2
        assert entries[0].role == "user"
        assert entries[0].content == "Hello"
        assert entries[1].role == "assistant"
        assert entries[1].content == "Hi there!"

    def test_load_recent_conversations_dict(self, database: Database):
        database.upsert_user("user_1", "telegram", "testuser")
        for i in range(5):
            database.save_conversation("user_1", "telegram", "chat_1", "user", f"msg_{i}", "godfather")
            database.save_conversation("user_1", "telegram", "chat_1", "assistant", f"resp_{i}", "godfather")

        result = database.load_recent_conversations_dict("user_1", "telegram", limit=4)
        assert len(result) == 4
        assert result[0]["role"] == "user"
        assert result[-1]["role"] == "assistant"

    def test_save_memory_and_recall(self, database: Database):
        database.save_memory("user_1", "fav_game", "Cyberpunk 2077")
        value = database.get_memory("user_1", "fav_game")
        assert value == "Cyberpunk 2077"

    def test_get_memory_nonexistent(self, database: Database):
        value = database.get_memory("user_1", "nothing")
        assert value is None

    def test_get_all_memories(self, database: Database):
        database.save_memory("user_1", "a", "alpha", category="cat1")
        database.save_memory("user_1", "b", "beta", category="cat2")
        database.save_memory("user_1", "c", "gamma", category="cat1")
        all_m = database.get_all_memories("user_1")
        assert len(all_m) == 3
        cat1 = database.get_all_memories("user_1", category="cat1")
        assert len(cat1) == 2
        cat2 = database.get_all_memories("user_1", category="cat2")
        assert len(cat2) == 1

    def test_delete_memory(self, database: Database):
        database.save_memory("user_1", "key1", "val1")
        assert database.delete_memory("user_1", "key1") is True
        assert database.delete_memory("user_1", "key1") is False

    def test_save_memory_overwrite(self, database: Database):
        database.save_memory("user_1", "key", "old")
        database.save_memory("user_1", "key", "new")
        assert database.get_memory("user_1", "key") == "new"

    def test_persona_state_save_load(self, database: Database):
        affinity = {"godfather": 0.9, "choom": 0.3}
        database.save_persona_state("tg:chat1:user1", "godfather", None, affinity, 100.0, 5, 3)
        loaded = database.load_persona_state("tg:chat1:user1")
        assert loaded is not None
        assert loaded["current"] == "godfather"
        assert loaded["transition_count"] == 5
        assert loaded["affinity"]["godfather"] == 0.9
        assert loaded["locked"] is False

    def test_persona_state_update(self, database: Database):
        database.save_persona_state("k", "godfather", None, {}, 1.0, 0, 0)
        database.save_persona_state("k", "choom", "godfather", {}, 2.0, 1, 0)
        loaded = database.load_persona_state("k")
        assert loaded["current"] == "choom"
        assert loaded["previous"] == "godfather"

    def test_allowed_groups(self, database: Database):
        assert database.is_group_allowed("chat_1") is False
        database.allow_group("chat_1", "Test Group", "admin1")
        assert database.is_group_allowed("chat_1") is True
        groups = database.list_allowed_groups()
        assert len(groups) == 1
        assert groups[0]["title"] == "Test Group"
        assert database.remove_group("chat_1") is True
        assert database.is_group_allowed("chat_1") is False
        assert database.remove_group("chat_1") is False

    def test_rate_limit_first_call(self, database: Database):
        ok, remaining = database.check_rate_limit("user_1", "/help", cooldown_seconds=5)
        assert ok is True
        assert remaining == 0.0

    def test_rate_limit_block(self, database: Database):
        database.check_rate_limit("user_1", "/help", cooldown_seconds=60)
        ok, remaining = database.check_rate_limit("user_1", "/help", cooldown_seconds=60)
        assert ok is False
        assert remaining > 0

    def test_rate_limit_per_command(self, database: Database):
        database.check_rate_limit("user_1", "/help", cooldown_seconds=60)
        ok, _ = database.check_rate_limit("user_1", "/status", cooldown_seconds=60)
        assert ok is True

    def test_rate_limit_per_user(self, database: Database):
        database.check_rate_limit("user_1", "/help", cooldown_seconds=60)
        ok, _ = database.check_rate_limit("user_2", "/help", cooldown_seconds=60)
        assert ok is True

    def test_ollama_stats(self, database: Database):
        database.log_ollama_call("http://localhost:11434", "llama3", 100, 500.0, True)
        database.log_ollama_call("http://localhost:11434", "llama3", 50, 300.0, True)
        database.log_ollama_call("http://localhost:11434", "llama3", 0, 0, False)
        stats = database.get_global_stats()
        assert stats["ollama_calls"] == 3

    def test_get_global_stats(self, database: Database):
        database.upsert_user("u1", "telegram", "a")
        database.upsert_user("u2", "telegram", "b")
        database.save_conversation("u1", "telegram", "c1", "user", "hi", "godfather", "llama3", 10)
        database.save_conversation("u1", "telegram", "c1", "assistant", "hey", "godfather", "llama3", 20)
        database.save_conversation("u2", "telegram", "c2", "user", "yo", "choom", "llama3", 15)
        stats = database.get_global_stats()
        assert stats["total_messages"] == 3
        assert stats["total_users"] == 2
        assert stats["total_tokens"] == 45

    def test_get_user_stats(self, database: Database):
        database.upsert_user("u1", "telegram", "test")
        database.save_conversation("u1", "telegram", "c1", "user", "hi", "godfather", "llama3", 10)
        database.save_conversation("u1", "telegram", "c1", "assistant", "hey", "choom", "llama3", 20)
        stats = database.get_user_stats("u1", "telegram")
        assert stats["total_messages"] == 2
        assert stats["personas_used"] == 2
        assert stats["total_tokens"] == 30
        assert stats["last_seen"] is not None
