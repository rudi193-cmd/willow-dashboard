"""Tests for dashboard UI helpers and sysinfo fetch.
b17: WDASH  ΔΣ=42
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock, patch
import dashboard


def test_sysinfo_fields_exist():
    assert hasattr(dashboard.DATA, "sys_cpu")
    assert hasattr(dashboard.DATA, "sys_mem")
    assert hasattr(dashboard.DATA, "sys_disk")
    assert hasattr(dashboard.DATA, "sys_tmp")


def test_fetch_sysinfo_populates_data():
    dashboard.fetch_sysinfo()
    assert isinstance(dashboard.DATA.sys_cpu, int)
    assert 0 <= dashboard.DATA.sys_cpu <= 100
    assert isinstance(dashboard.DATA.sys_mem, int)
    assert 0 <= dashboard.DATA.sys_mem <= 100
    assert isinstance(dashboard.DATA.sys_disk, int)
    assert 0 <= dashboard.DATA.sys_disk <= 100
    assert isinstance(dashboard.DATA.sys_tmp, int)


def test_ascii_bar_empty():
    assert dashboard._ascii_bar(0, 8) == "░░░░░░░░"


def test_ascii_bar_full():
    assert dashboard._ascii_bar(100, 8) == "████████"


def test_ascii_bar_half():
    assert dashboard._ascii_bar(50, 8) == "████░░░░"


def test_ascii_bar_width():
    result = dashboard._ascii_bar(75, 10)
    assert len(result) == 10
    assert result.count("█") == 8  # round(75/100*10) = 7.5 rounds to 8


def _make_win(h=20, w=40):
    """Return a mock curses window."""
    win = MagicMock()
    win.getmaxyx.return_value = (h, w)
    return win


def test_draw_agents_region_empty():
    import dashboard
    win = _make_win()
    with patch("curses.color_pair", return_value=0), patch("curses.A_DIM", 0):
        y = dashboard._draw_agents_region(win, 0, 40, [])
    assert y > 0  # header row consumed at minimum


def test_draw_agents_region_shows_agents():
    import dashboard
    agents = [
        {"sender": "hanuman",    "age_secs": 30},
        {"sender": "heimdallr",  "age_secs": 200},
        {"sender": "oakenscroll","age_secs": 4000},  # gone, should be skipped
    ]
    win = _make_win()
    with patch("curses.color_pair", return_value=0), patch("curses.A_DIM", 0):
        y = dashboard._draw_agents_region(win, 0, 40, agents)
    assert y >= 3  # header + 2 visible agents (gone skipped)


def test_draw_grove_region_empty():
    import dashboard
    win = _make_win()
    with patch("curses.color_pair", return_value=0):
        y = dashboard._draw_grove_region(win, 0, 40, [])
    assert y > 0


def test_draw_grove_region_shows_unread():
    import dashboard
    channels = [
        {"name": "general",      "unread": 0},
        {"name": "architecture", "unread": 3},
    ]
    win = _make_win()
    with patch("curses.color_pair", return_value=0):
        y = dashboard._draw_grove_region(win, 0, 40, channels)
    assert y >= 3  # header + 2 channels


def test_draw_routing_region_empty():
    import dashboard
    win = _make_win()
    with patch("curses.color_pair", return_value=0):
        y = dashboard._draw_routing_region(win, 0, 40, [])
    assert y > 0  # still renders "no routing decisions" line


def test_draw_routing_region_shows_decision():
    import dashboard
    from datetime import datetime, timezone
    decisions = [{
        "ts": datetime(2026, 4, 22, 13, 4, tzinfo=timezone.utc),
        "prompt_snippet": "debug gleipnir",
        "routed_to": "ganesha",
        "rule_matched": "rule-debug",
        "confidence": 0.95,
        "latency_ms": 3,
    }]
    win = _make_win()
    with patch("curses.color_pair", return_value=0), patch("curses.A_DIM", 0):
        y = dashboard._draw_routing_region(win, 0, 40, decisions)
    assert y >= 2  # header + 1 row
