"""test_skins.py — unit tests for skins.py
b17: WDASH  ΔΣ=42
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Stub curses before import so COLOR_* constants resolve
import curses as _curses
for _attr in ("COLOR_WHITE","COLOR_BLUE","COLOR_GREEN","COLOR_YELLOW",
              "COLOR_RED","COLOR_CYAN","COLOR_MAGENTA"):
    if not hasattr(_curses, _attr):
        setattr(_curses, _attr, 0)


import skins
import soil


@pytest.fixture(autouse=True)
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setenv("WILLOW_STORE_ROOT", str(tmp_path))


def test_skin_seeds_count():
    assert len(skins.SKIN_SEEDS) == 5


def test_skin_ids():
    ids = {s.id for s in skins.SKIN_SEEDS}
    assert ids == {"default", "midnight", "forest", "amber", "accessible"}


def test_accessible_skin_flag():
    acc = next(s for s in skins.SKIN_SEEDS if s.id == "accessible")
    assert acc.accessible is True


def test_non_accessible_skins_not_accessible():
    for s in skins.SKIN_SEEDS:
        if s.id != "accessible":
            assert s.accessible is False


def test_skin_to_dict_roundtrip():
    s = skins.SKIN_SEEDS[0]
    d = s.to_dict()
    s2 = skins.Skin.from_dict(d)
    assert s2.id == s.id
    assert s2.accessible == s.accessible
    assert s2.grid_columns == s.grid_columns


def test_seed_writes_to_soil():
    skins.seed()
    recs = soil.all_records("willow-dashboard/skins")
    assert len(recs) == 5
    ids = {r["id"] for r in recs}
    assert "default" in ids
    assert "accessible" in ids


def test_seed_idempotent():
    skins.seed()
    skins.seed()
    recs = soil.all_records("willow-dashboard/skins")
    assert len(recs) == 5


def test_load_returns_default_when_no_config():
    skins.seed()
    skin = skins.load()
    assert skin.id == "default"


def test_load_returns_configured_skin():
    skins.seed()
    skins.set_active("amber")
    skin = skins.load()
    assert skin.id == "amber"


def test_set_active_persists():
    skins.seed()
    skins.set_active("midnight")
    cfg = soil.get("willow-dashboard/config", "active_skin")
    assert cfg["value"] == "midnight"


def test_state_symbols_present():
    assert "green" in skins.STATE_SYMBOLS
    assert "amber" in skins.STATE_SYMBOLS
    assert "red" in skins.STATE_SYMBOLS


def test_symbol_key_string():
    assert "✓" in skins.SYMBOL_KEY
    assert "▲" in skins.SYMBOL_KEY
