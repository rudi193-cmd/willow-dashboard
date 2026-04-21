"""test_soil.py — unit tests for soil.py
b17: WDASH  ΔΣ=42
"""
import os
import tempfile
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soil


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))


def test_put_and_get():
    soil.put("test/col", "rec1", {"name": "alpha", "val": 42})
    rec = soil.get("test/col", "rec1")
    assert rec["name"] == "alpha"
    assert rec["val"] == 42
    assert rec["_id"] == "rec1"


def test_get_missing_returns_none():
    assert soil.get("test/col", "nope") is None


def test_get_missing_collection_returns_none():
    assert soil.get("test/does-not-exist", "x") is None


def test_upsert_updates_record():
    soil.put("test/col", "rec1", {"val": 1})
    soil.put("test/col", "rec1", {"val": 2})
    rec = soil.get("test/col", "rec1")
    assert rec["val"] == 2


def test_all_records_empty():
    assert soil.all_records("test/empty") == []


def test_all_records_multiple():
    soil.put("test/col", "a", {"x": 1})
    soil.put("test/col", "b", {"x": 2})
    soil.put("test/col", "c", {"x": 3})
    recs = soil.all_records("test/col")
    assert len(recs) == 3
    ids = {r["_id"] for r in recs}
    assert ids == {"a", "b", "c"}


def test_query_raw_sql():
    soil.put("test/col", "r1", {"score": 10})
    soil.put("test/col", "r2", {"score": 20})
    rows = soil.query("test/col", "SELECT COUNT(*) FROM records WHERE deleted=0")
    assert rows[0][0] == 2


def test_query_one():
    soil.put("test/col", "r1", {"v": 5})
    row = soil.query_one("test/col", "SELECT COUNT(*) FROM records WHERE deleted=0")
    assert row is not None
    assert row[0] == 1


def test_query_missing_collection_returns_empty():
    assert soil.query("test/ghost", "SELECT 1") == []


def test_deleted_flag_respected():
    soil.put("test/col", "del1", {"v": 9})
    # Soft-delete by setting deleted=1 directly
    import sqlite3
    db = soil._db("test/col")
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE records SET deleted=1 WHERE id='del1'")
    conn.commit()
    conn.close()
    assert soil.get("test/col", "del1") is None
    recs = soil.all_records("test/col")
    assert all(r["_id"] != "del1" for r in recs)
