"""Tests for dashboard UI helpers and sysinfo fetch."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

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
