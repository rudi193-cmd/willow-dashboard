"""soil.py — thin sqlite3 wrapper for SOIL collections used by the dashboard.
b17: WDASH  ΔΣ=42
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def _root() -> Path:
    return Path(os.environ.get("WILLOW_STORE_ROOT", str(Path.home() / ".willow" / "store")))


def _db(collection: str) -> Path:
    p = _root() / Path(collection)
    p.mkdir(parents=True, exist_ok=True)
    return p / "store.db"


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def put(collection: str, record_id: str, record: dict) -> None:
    """Insert or update a record. Safe to call multiple times (upsert)."""
    db = _db(collection)
    conn = _conn(db)
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO records (id, data, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
    """, (record_id, json.dumps(record, default=str), now, now))
    conn.commit()
    conn.close()


def get(collection: str, record_id: str) -> dict | None:
    db = _db(collection)
    if not db.exists():
        return None
    conn = _conn(db)
    row = conn.execute(
        "SELECT data FROM records WHERE id=? AND deleted=0", (record_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    rec = json.loads(row[0])
    rec["_id"] = record_id
    return rec


def all_records(collection: str) -> list[dict]:
    db = _db(collection)
    if not db.exists():
        return []
    conn = _conn(db)
    rows = conn.execute(
        "SELECT id, data FROM records WHERE deleted=0 ORDER BY created_at"
    ).fetchall()
    conn.close()
    result = []
    for rid, data in rows:
        rec = json.loads(data)
        rec["_id"] = rid
        result.append(rec)
    return result


def query(collection: str, sql: str) -> list[tuple]:
    """Run a raw SQL query against a SOIL collection's store.db."""
    db = _db(collection)
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql).fetchall()
    except Exception:
        return []
    finally:
        conn.close()


def query_one(collection: str, sql: str) -> tuple | None:
    rows = query(collection, sql)
    return rows[0] if rows else None
