#!/usr/bin/env python3
"""Archive and selectively import LP_Godfather_Deploy SQLite data into v4.

The source database is opened read-only. Every source row is retained as JSON in
``legacy_records``. Only conversation history and user facts are mapped into v4
runtime tables; moderation/configuration data remains archived for manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: object) -> float:
    if not value:
        return time.time()
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return time.time()


def source_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in source_tables(conn)
    }


def ensure_target_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS legacy_records (
            source_table TEXT NOT NULL,
            source_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            imported_at REAL NOT NULL,
            PRIMARY KEY (source_table, source_id)
        );
        CREATE TABLE IF NOT EXISTS legacy_imports (
            source_sha256 TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            imported_at REAL NOT NULL
        );
    """)


def archive_row(target: sqlite3.Connection, table: str, row: sqlite3.Row) -> bool:
    payload = dict(row)
    source_id = str(payload.get("id", payload.get("key", json.dumps(payload, sort_keys=True))))
    cursor = target.execute(
        "INSERT OR IGNORE INTO legacy_records "
        "(source_table, source_id, payload, imported_at) VALUES (?, ?, ?, ?)",
        (table, source_id, json.dumps(payload, ensure_ascii=False, sort_keys=True), time.time()),
    )
    return cursor.rowcount == 1


def map_user_fact(target: sqlite3.Connection, row: sqlite3.Row) -> None:
    user_id = str(row["user_id"])
    timestamp = parse_timestamp(row["created_at"])
    target.execute(
        "INSERT OR IGNORE INTO users "
        "(id, platform, username, first_seen, last_seen, total_messages) "
        "VALUES (?, 'telegram', NULL, ?, ?, 0)",
        (user_id, timestamp, timestamp),
    )
    target.execute(
        "INSERT OR IGNORE INTO user_memories "
        "(user_id, key, value, category, created_at, updated_at) "
        "VALUES (?, ?, ?, 'legacy_fact', ?, ?)",
        (user_id, f"legacy_fact_{row['id']}", row["fact_text"], timestamp, timestamp),
    )


def map_conversation(target: sqlite3.Connection, row: sqlite3.Row) -> None:
    user_id = str(row["user_id"])
    timestamp = parse_timestamp(row["created_at"])
    target.execute(
        "INSERT OR IGNORE INTO users "
        "(id, platform, username, first_seen, last_seen, total_messages) "
        "VALUES (?, 'telegram', NULL, ?, ?, 0)",
        (user_id, timestamp, timestamp),
    )
    target.execute(
        "INSERT INTO conversations "
        "(user_id, platform, chat_id, role, content, persona, timestamp) "
        "VALUES (?, 'telegram', 'legacy', ?, ?, 'godfather', ?)",
        (user_id, row["role"], row["content"], timestamp),
    )


def import_database(source: Path, target: Path) -> dict[str, int]:
    source_uri = f"file:{source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as old, sqlite3.connect(target) as new:
        old.row_factory = sqlite3.Row
        new.row_factory = sqlite3.Row
        ensure_target_schema(new)
        imported: dict[str, int] = {}
        for table in source_tables(old):
            imported[table] = 0
            for row in old.execute(f'SELECT * FROM "{table}"'):
                if not archive_row(new, table, row):
                    continue
                imported[table] += 1
                if table == "user_facts":
                    map_user_fact(new, row)
                elif table == "conversation_history":
                    map_conversation(new, row)
        new.execute(
            "INSERT OR REPLACE INTO legacy_imports "
            "(source_sha256, source_path, imported_at) VALUES (?, ?, ?)",
            (source_hash(source), str(source.resolve()), time.time()),
        )
        new.commit()
    return imported


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--apply", action="store_true", help="perform import; default is dry-run")
    args = parser.parse_args()

    if not args.source.is_file() or not args.target.is_file():
        parser.error("source and target must be existing database files")
    if args.source.resolve() == args.target.resolve():
        parser.error("source and target must differ")

    source_uri = f"file:{args.source.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as conn:
        counts = table_counts(conn)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "tables": counts}, sort_keys=True))
    if not args.apply:
        return 0

    backup = args.target.with_suffix(args.target.suffix + f".pre-import-{int(time.time())}")
    shutil.copy2(args.target, backup)
    imported = import_database(args.source, args.target)
    print(json.dumps({"backup": str(backup), "imported": imported}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

