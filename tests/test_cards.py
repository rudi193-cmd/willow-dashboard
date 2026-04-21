"""test_cards.py — unit tests for cards.py
b17: WDASH  ΔΣ=42
"""
import sys
import json
import re
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import curses as _curses
for _attr in ("COLOR_WHITE","COLOR_BLUE","COLOR_GREEN","COLOR_YELLOW",
              "COLOR_RED","COLOR_CYAN","COLOR_MAGENTA",
              "A_BOLD","A_REVERSE","A_UNDERLINE"):
    if not hasattr(_curses, _attr):
        setattr(_curses, _attr, 0)

import skins
import cards as card_mod
import soil


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    # Reset module-level _CARD_MAP after seed so tests start clean
    yield


# ── Seed catalog ──────────────────────────────────────────────────────────────

def test_seed_catalog_size():
    assert len(card_mod.CARD_SEEDS) == 19  # 7 built-in + 12 optional


def test_built_in_count():
    built_ins = [c for c in card_mod.CARD_SEEDS if c.built_in]
    assert len(built_ins) == 7


def test_optional_count():
    optional = [c for c in card_mod.CARD_SEEDS if not c.built_in]
    assert len(optional) == 12


def test_built_ins_enabled():
    for c in card_mod.CARD_SEEDS:
        if c.built_in:
            assert c.enabled is True, f"{c.id} should be enabled"


def test_optional_disabled():
    for c in card_mod.CARD_SEEDS:
        if not c.built_in:
            assert c.enabled is False, f"{c.id} should start disabled"


def test_built_in_ids():
    expected = {"kart","knowledge","yggdrasil","agents","secrets","fleet","mcp"}
    actual = {c.id for c in card_mod.CARD_SEEDS if c.built_in}
    assert actual == expected


# ── SOIL seed / load ──────────────────────────────────────────────────────────

def test_seed_cards_writes_soil():
    card_mod.seed_cards()
    recs = soil.all_records("willow-dashboard/cards")
    assert len(recs) == 19


def test_seed_cards_idempotent():
    card_mod.seed_cards()
    card_mod.seed_cards()
    recs = soil.all_records("willow-dashboard/cards")
    assert len(recs) == 19


def test_load_cards_returns_only_enabled():
    card_mod.seed_cards()
    loaded = card_mod.load_cards()
    assert all(c.enabled for c in loaded)


def test_load_cards_sorted_by_order():
    card_mod.seed_cards()
    loaded = card_mod.load_cards()
    orders = [c.order for c in loaded]
    assert orders == sorted(orders)


def test_load_cards_built_ins_only_by_default():
    card_mod.seed_cards()
    loaded = card_mod.load_cards()
    assert len(loaded) == 7


def test_save_card_enables_optional():
    card_mod.seed_cards()
    notes = card_mod.CardDef.from_dict(soil.get("willow-dashboard/cards", "notes"))
    notes.enabled = True
    card_mod.save_card(notes)
    loaded = card_mod.load_cards()
    ids = {c.id for c in loaded}
    assert "notes" in ids


# ── CardDef dataclass ─────────────────────────────────────────────────────────

def test_carddef_to_dict_roundtrip():
    c = card_mod.CARD_SEEDS[0]
    d = c.to_dict()
    c2 = card_mod.CardDef.from_dict(d)
    assert c2.id == c.id
    assert c2.built_in == c.built_in
    assert c2.actions == c.actions


def test_carddef_from_dict_ignores_unknown_fields():
    d = {"id": "x", "label": "X", "unknown_field": "ignored"}
    c = card_mod.CardDef.from_dict(d)
    assert c.id == "x"
    assert not hasattr(c, "unknown_field")


# ── Query runner ──────────────────────────────────────────────────────────────

def test_run_card_query_empty_sql_returns_empty():
    c = card_mod.CardDef(id="t", label="T")
    assert card_mod._run_card_query(c, "") == ""


def test_run_card_query_soil():
    card_mod.seed_cards()
    soil.put("test/items", "i1", {"status": "active"})
    soil.put("test/items", "i2", {"status": "active"})
    c = card_mod.CardDef(
        id="t", label="T",
        soil_collection="test/items",
        value_query="SELECT COUNT(*) FROM records WHERE deleted=0",
    )
    result = card_mod._run_card_query(c, c.value_query)
    assert result == "2"


def test_run_card_query_no_source_returns_empty():
    c = card_mod.CardDef(id="t", label="T", value_query="SELECT 1")
    assert card_mod._run_card_query(c, c.value_query) == ""


# ── Accessible skin symbols ───────────────────────────────────────────────────

def test_state_symbols_map():
    assert skins.STATE_SYMBOLS["green"] == "✓"
    assert skins.STATE_SYMBOLS["amber"] == "▲"
    assert skins.STATE_SYMBOLS["red"]   == "✗"
    assert skins.STATE_SYMBOLS["blue"]  == "●"


# ── card-def block parsing ─────────────────────────────────────────────────────

_CARD_DEF_RE = re.compile(r"```card-def\s*\n(\{.*?\})\s*\n```", re.DOTALL)

def test_card_def_block_matched():
    reply = (
        "Sure! Here's your card:\n"
        "```card-def\n"
        '{"id":"todos","label":"TODOs","category":"dev","built_in":false,"enabled":true,'
        '"order":50,"value_query":"SELECT COUNT(*) FROM todos","sub_format":"open items",'
        '"soil_collection":"","pg_table":"public.todos"}\n'
        "```\n"
    )
    m = _CARD_DEF_RE.search(reply)
    assert m is not None
    d = json.loads(m.group(1))
    assert d["id"] == "todos"
    assert d["label"] == "TODOs"


def test_card_def_block_not_matched_without_fence():
    reply = '{"id":"x","label":"X","built_in":false,"enabled":true}'
    assert _CARD_DEF_RE.search(reply) is None


def test_card_def_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))
    card_mod.seed_cards()
    d = {
        "id": "my-custom", "label": "My Custom", "category": "work",
        "built_in": False, "enabled": True, "order": 50,
        "value_query": "SELECT COUNT(*) FROM records WHERE deleted=0",
        "sub_format": "records", "soil_collection": "my-collection", "pg_table": "",
    }
    c = card_mod.CardDef.from_dict(d)
    card_mod.save_card(c)
    loaded = [x for x in card_mod.load_cards() if x.id == "my-custom"]
    assert len(loaded) == 1
    assert loaded[0].label == "My Custom"
    assert loaded[0].soil_collection == "my-collection"
