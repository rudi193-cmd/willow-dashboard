# UI Mission Control Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard look and feel like a live ops room — dense status column, vitals strip in the hero bar, command interface as the chat panel centerpiece.

**Architecture:** Chrome-first — add `fetch_sysinfo()` for CPU/MEM/DISK/TEMP, add `_ascii_bar()` and `_section_header()` helpers, replace the hero hline with an inline vitals strip, replace the Overview right panel card grid with a compact STATUS column, add a COMMAND section header to the left panel, tighten nav bar contrast.

**Tech Stack:** Python 3, stdlib curses, `/proc/stat`, `/proc/meminfo`, `shutil.disk_usage`, `/sys/class/thermal`

---

## File Map

| File | Change |
|------|--------|
| `dashboard.py` | All changes — sysinfo fields on `SystemData`, `fetch_sysinfo()`, `_ascii_bar()`, `_section_header()`, `_draw_hero_vitals()`, updated `draw_willow_hero()`, new `draw_overview_right()`, updated `draw_overview_left()`, updated `draw_page_bar()` |
| `tests/test_dashboard_ui.py` | New — unit tests for `_ascii_bar()` and `fetch_sysinfo()` |

No other files change.

---

### Task 1: Sysinfo fields on SystemData + fetch_sysinfo()

**Files:**
- Modify: `dashboard.py` — `SystemData.__init__` and new `fetch_sysinfo()` function, `refresh_all()`
- Create: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_ui.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /home/sean-campbell/github/willow-dashboard
python -m pytest tests/test_dashboard_ui.py -v
```

Expected: `AttributeError: 'SystemData' object has no attribute 'sys_cpu'`

- [ ] **Step 3: Add sysinfo fields to SystemData.__init__**

In `dashboard.py`, find `class SystemData:` (line ~630). Add these fields to `__init__` after `self.log`:

```python
        # sysinfo — populated by fetch_sysinfo()
        self.sys_cpu  = 0   # 0-100 %
        self.sys_mem  = 0   # 0-100 %
        self.sys_disk = 0   # 0-100 %
        self.sys_tmp  = 0   # degrees C
        self._prev_cpu_stat: tuple[int, int] | None = None  # (total, idle)
```

- [ ] **Step 4: Add fetch_sysinfo() after fetch_agents() (line ~942)**

```python
def _read_proc_cpu() -> tuple[int, int]:
    """Return (total_jiffies, idle_jiffies) from /proc/stat cpu line."""
    with open("/proc/stat") as f:
        parts = f.readline().split()
    vals = [int(x) for x in parts[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    return sum(vals), idle


def fetch_sysinfo() -> None:
    # CPU — delta between two readings
    try:
        curr_total, curr_idle = _read_proc_cpu()
        with DATA.lock:
            prev = DATA._prev_cpu_stat
            DATA._prev_cpu_stat = (curr_total, curr_idle)
        if prev:
            dt = curr_total - prev[0]
            di = curr_idle - prev[1]
            pct = int((1 - di / max(dt, 1)) * 100)
            with DATA.lock:
                DATA.sys_cpu = max(0, min(100, pct))
    except Exception:
        pass

    # MEM — MemTotal and MemAvailable from /proc/meminfo
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k.strip()] = int(v.strip().split()[0])
        total = info.get("MemTotal", 1)
        avail = info.get("MemAvailable", total)
        pct = int((total - avail) / total * 100)
        with DATA.lock:
            DATA.sys_mem = max(0, min(100, pct))
    except Exception:
        pass

    # DISK — root filesystem usage
    try:
        import shutil
        usage = shutil.disk_usage("/")
        pct = int(usage.used / usage.total * 100)
        with DATA.lock:
            DATA.sys_disk = max(0, min(100, pct))
    except Exception:
        pass

    # TEMP — first thermal zone (Linux sysfs)
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            tmp = int(f.read().strip()) // 1000
        with DATA.lock:
            DATA.sys_tmp = tmp
    except Exception:
        pass
```

- [ ] **Step 5: Wire into refresh_all()**

In `refresh_all()` (line ~944), add `fetch_sysinfo()` as the first call:

```python
def refresh_all():
    with DATA.lock:
        DATA.ts = datetime.now().strftime("%H:%M:%S")
    DATA.push_log("── refreshing ──")
    fetch_sysinfo()          # ← add this line
    fetch_postgres()
    fetch_ollama()
    ...
```

- [ ] **Step 6: Run tests to verify they pass**

```
python -m pytest tests/test_dashboard_ui.py::test_sysinfo_fields_exist tests/test_dashboard_ui.py::test_fetch_sysinfo_populates_data -v
```

Expected: both PASS

- [ ] **Step 7: Commit**

```bash
git add dashboard.py tests/test_dashboard_ui.py
git commit -m "feat: add sysinfo fetch (CPU/MEM/DISK/TEMP) to SystemData"
```

---

### Task 2: _ascii_bar() and _section_header() helpers

**Files:**
- Modify: `dashboard.py` — two new functions in the Drawing helpers block (line ~962)
- Modify: `tests/test_dashboard_ui.py` — add bar tests

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dashboard_ui.py`:

```python
def test_ascii_bar_empty():
    assert dashboard._ascii_bar(0, 8) == "░░░░░░░░"


def test_ascii_bar_full():
    assert dashboard._ascii_bar(100, 8) == "████████"


def test_ascii_bar_half():
    assert dashboard._ascii_bar(50, 8) == "████░░░░"


def test_ascii_bar_width():
    result = dashboard._ascii_bar(75, 10)
    assert len(result) == 10
    assert result.count("█") == 8  # round(75/100*10) = 8 (actually 7.5 rounds to 8)
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_dashboard_ui.py::test_ascii_bar_empty -v
```

Expected: `AttributeError: module 'dashboard' has no attribute '_ascii_bar'`

- [ ] **Step 3: Add _ascii_bar() to dashboard.py**

In the Drawing helpers block (after `draw_hline`, around line ~975), add:

```python
def _ascii_bar(pct: int, width: int = 8) -> str:
    """Return a filled/empty block bar string representing pct (0-100)."""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)
```

- [ ] **Step 4: Add _section_header() after _ascii_bar()**

```python
def _section_header(win, y: int, label: str) -> None:
    """Draw a full-width ── LABEL ──── rule at row y."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h:
        return
    prefix = f"── {label} "
    fill = max(0, w - len(prefix) - 1)
    line = prefix + "─" * fill
    try:
        win.addstr(y, 0, line[:w - 1], curses.color_pair(C_BLUE) | curses.A_BOLD)
    except curses.error:
        pass
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_dashboard_ui.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard.py tests/test_dashboard_ui.py
git commit -m "feat: add _ascii_bar() and _section_header() drawing helpers"
```

---

### Task 3: Hero vitals strip (replace plain hline)

**Files:**
- Modify: `dashboard.py` — new `_draw_hero_vitals()`, updated `draw_willow_hero()`

- [ ] **Step 1: Add _draw_hero_vitals() after _section_header()**

```python
def _draw_hero_vitals(win, y: int) -> None:
    """Draw CPU/MEM/DISK/TEMP inline vitals strip at row y."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h:
        return
    with DATA.lock:
        cpu  = DATA.sys_cpu
        mem  = DATA.sys_mem
        disk = DATA.sys_disk
        tmp  = DATA.sys_tmp

    bar_w = 6
    parts: list[tuple[str, str, str, int]] = [
        ("CPU ", _ascii_bar(cpu, bar_w),  f" {cpu:2d}%",  cpu),
        (" MEM ", _ascii_bar(mem, bar_w), f" {mem:2d}%",  mem),
        (" DISK ", _ascii_bar(disk, bar_w), f" {disk:2d}%", disk),
    ]

    try:
        win.hline(y, 0, curses.ACS_HLINE, w - 1, curses.color_pair(C_DIM))
    except curses.error:
        pass

    x = 1
    for label, bar, val, pct in parts:
        if x + len(label) + bar_w + len(val) + 2 >= w:
            break
        safe_addstr(win, y, x, label, curses.color_pair(C_DIM))
        x += len(label)
        bar_col = C_AMBER if pct > 85 else C_BLUE
        safe_addstr(win, y, x, bar, curses.color_pair(bar_col))
        x += bar_w
        safe_addstr(win, y, x, val, curses.color_pair(C_DIM))
        x += len(val)

    # TMP — no bar, just the number
    tmp_col = C_AMBER if tmp > 70 else C_DIM
    tmp_str = f" TMP {tmp}°C"
    if x + len(tmp_str) < w - 1:
        safe_addstr(win, y, x, tmp_str, curses.color_pair(tmp_col))
```

- [ ] **Step 2: Update draw_willow_hero() to call _draw_hero_vitals()**

Find this line in `draw_willow_hero()` (line ~1065):

```python
    draw_hline(win, _TREE_H + 2, curses.color_pair(C_DIM))
    return _TREE_H + 3
```

Replace with:

```python
    _draw_hero_vitals(win, _TREE_H + 2)
    return _TREE_H + 3
```

- [ ] **Step 3: Smoke test**

```
cd /home/sean-campbell/github/willow-dashboard
python3 dashboard.py
```

Expected: hero bar bottom row shows `CPU ░░░░░░ 0%  MEM ██░░░░ XX%  DISK ██░░░░ XX%  TMP XX°C` (CPU will be 0 until second refresh populates the delta).

Press `r` to force a refresh. CPU % should populate on the second refresh.

- [ ] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "feat: replace hero hline with live vitals strip (CPU/MEM/DISK/TMP)"
```

---

### Task 4: Replace Overview right panel with STATUS column

**Files:**
- Modify: `dashboard.py` — `draw_overview_right()`

- [ ] **Step 1: Replace draw_overview_right() with the STATUS column**

Find `def draw_overview_right(win):` (line ~1265). Replace the entire function with:

```python
def draw_overview_right(win):
    if shutdown_mod.SHUTDOWN.active:
        draw_shutdown_right(win)
        return
    h, w = win.getmaxyx()
    win.erase()
    focused = NAV.focus == "right"

    with DATA.lock:
        pg_kb       = DATA.pg_knowledge
        pg_edges    = DATA.pg_edges
        kp          = DATA.kart_pending
        kr          = DATA.kart_running
        kd          = DATA.kart_done
        ollama_up   = DATA.ollama_running
        ygg         = DATA.ollama_ygg
        safe_p      = DATA.manifests_pass
        safe_t      = DATA.manifests_total
        cpu         = DATA.sys_cpu
        mem         = DATA.sys_mem
        disk        = DATA.sys_disk
        tmp         = DATA.sys_tmp
        tasks       = DATA.kart_tasks[:3]

    y = 0
    _section_header(win, y, "STATUS"); y += 1

    # Postgres / LOAM
    safe_addstr(win, y, 1, "● Postgres", curses.color_pair(C_GREEN)); y += 1
    safe_addstr(win, y, 3, f"{pg_kb} atoms · {pg_edges} edges",
                curses.color_pair(C_DIM)); y += 1

    # Kart
    try:
        kp_warn = int(kp) > 0
    except (ValueError, TypeError):
        kp_warn = False
    kart_dot = "▲" if kp_warn else "●"
    kart_col = C_AMBER if kp_warn else C_GREEN
    safe_addstr(win, y, 1, f"{kart_dot} Kart",
                curses.color_pair(kart_col) | (curses.A_BOLD if kp_warn else 0)); y += 1
    safe_addstr(win, y, 3, f"{kp}q · {kr}r · {kd}d",
                curses.color_pair(C_DIM)); y += 1

    # Ollama
    ollama_dot = "●" if ollama_up else "✗"
    ollama_col = C_GREEN if ollama_up else C_RED
    safe_addstr(win, y, 1, f"{ollama_dot} Ollama",
                curses.color_pair(ollama_col)); y += 1
    state_str = "warm" if ollama_up else "down"
    safe_addstr(win, y, 3, f"{ygg} · {state_str}",
                curses.color_pair(C_DIM)); y += 1

    # SAFE
    try:
        safe_ok = int(safe_p) == int(safe_t) and int(safe_t) > 0
    except (ValueError, TypeError):
        safe_ok = False
    safe_dot = "●" if safe_ok else "▲"
    safe_col = C_GREEN if safe_ok else C_AMBER
    safe_addstr(win, y, 1, f"{safe_dot} SAFE",
                curses.color_pair(safe_col)); y += 1
    safe_addstr(win, y, 3, f"{safe_p}/{safe_t} signed",
                curses.color_pair(C_DIM)); y += 1

    # VITALS
    if y < h - 7:
        _section_header(win, y, "VITALS"); y += 1
        bar_w = max(4, w - 12)
        for label, pct, threshold in [
            ("CPU", cpu, 85),
            ("MEM", mem, 90),
            ("DSK", disk, 85),
        ]:
            if y >= h - 4:
                break
            bar = _ascii_bar(pct, bar_w)
            bar_col = C_AMBER if pct > threshold else C_GREEN
            safe_addstr(win, y, 1, f"{label} ", curses.color_pair(C_DIM))
            safe_addstr(win, y, 5, bar, curses.color_pair(bar_col))
            safe_addstr(win, y, 5 + bar_w, f" {pct:2d}%", curses.color_pair(C_DIM))
            y += 1
        # TMP inline
        if y < h - 4:
            tmp_col = C_AMBER if tmp > 70 else C_DIM
            safe_addstr(win, y, 1, f"TMP {tmp}°C", curses.color_pair(tmp_col)); y += 1

    # QUEUE — recent kart tasks
    if y < h - 3 and tasks:
        _section_header(win, y, "QUEUE"); y += 1
        for t in tasks:
            if y >= h - 2:
                break
            cmd_w = max(1, w - 4)
            safe_addstr(win, y, 1, f"{t['cmd'][:cmd_w]}",
                        curses.color_pair(C_DIM)); y += 1

    draw_panel_border(win, focused)
    win.noutrefresh()
```

- [ ] **Step 2: Smoke test**

```
python3 dashboard.py
```

Expected: Overview right panel shows STATUS section with Postgres/Kart/Ollama/SAFE dots + inline metrics, VITALS bars, and QUEUE tasks. No card grid.

Tab to focus right panel — amber border appears. No crashes.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: replace overview right panel with STATUS column (dot+metrics, vitals, queue)"
```

---

### Task 5: COMMAND section header in draw_overview_left()

**Files:**
- Modify: `dashboard.py` — `draw_overview_left()`

- [ ] **Step 1: Add _section_header after hero return**

Find `draw_overview_left()` (line ~1143). Find this block:

```python
    content_y = draw_willow_hero(win)
    focused   = NAV.focus == "left"

    # ── Chat history ──
    input_row  = h - 3
```

Replace with:

```python
    content_y = draw_willow_hero(win)
    focused   = NAV.focus == "left"

    _section_header(win, content_y, "COMMAND")
    content_y += 1

    # ── Chat history ──
    input_row  = h - 3
```

- [ ] **Step 2: Smoke test**

```
python3 dashboard.py
```

Expected: a `── COMMAND ──────────────` header line appears between the hero block and the first chat message. Chat history and input still work normally.

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: add COMMAND section header to overview left panel"
```

---

### Task 6: Nav bar contrast

**Files:**
- Modify: `dashboard.py` — `draw_page_bar()`

- [ ] **Step 1: Tighten inactive tab attr**

Find `draw_page_bar()` (line ~1112). Find this block:

```python
        if active:
            tab_col = C_AMBER if NAV.focus is not None else C_BLUE
            attr = curses.color_pair(tab_col) | curses.A_BOLD | curses.A_REVERSE
        else:
            attr = curses.color_pair(C_DIM)
```

Replace with:

```python
        if active:
            tab_col = C_AMBER if NAV.focus is not None else C_BLUE
            attr = curses.color_pair(tab_col) | curses.A_BOLD | curses.A_REVERSE
        else:
            attr = curses.color_pair(C_DIM) | curses.A_DIM
```

- [ ] **Step 2: Smoke test**

```
python3 dashboard.py
```

Expected: active page tab is bright amber/blue on reverse background. Inactive page tabs are visibly dimmer. Navigate with ←→ to confirm contrast is legible.

- [ ] **Step 3: Run full test suite**

```
python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "feat: increase nav bar contrast — inactive tabs dimmed, active amber+reverse"
```

---

## Self-Review

**Spec coverage:**
- ✓ Hero footer vitals strip — Task 3
- ✓ `_section_header()` helper used across Overview — Tasks 2, 4, 5
- ✓ Page nav bar contrast — Task 6
- ✓ Left panel COMMAND header — Task 5
- ✓ Right panel STATUS column (dot+metrics, VITALS bars, QUEUE) — Task 4
- ✓ `_ascii_bar()` utility — Task 2
- ✓ `fetch_sysinfo()` for CPU/MEM/DISK/TEMP — Task 1
- ✓ No other pages structurally changed

**Placeholder scan:** None found.

**Type consistency:**
- `_ascii_bar(pct: int, width: int) -> str` — used in `_draw_hero_vitals()` (Task 3) and `draw_overview_right()` (Task 4): consistent
- `_section_header(win, y: int, label: str)` — used in Tasks 4 and 5: consistent
- `DATA.sys_cpu`, `DATA.sys_mem`, `DATA.sys_disk`, `DATA.sys_tmp` — defined in Task 1, read in Tasks 3 and 4: consistent
- `_read_proc_cpu() -> tuple[int, int]` — called only inside `fetch_sysinfo()`: consistent
