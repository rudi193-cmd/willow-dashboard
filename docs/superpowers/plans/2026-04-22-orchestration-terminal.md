# Orchestration Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add AGENTS, ROUTING, and GROVE always-visible regions to the overview right panel, plus a nuke placard triggered by `n`.

**Architecture:** New `grove_reader.py` module handles all Postgres reads against `grove.*` and `willow.routing_decisions`. `SystemData` gets three new fields populated by `fetch_grove()` in the background thread. Three new renderer functions (`_draw_agents_region`, `_draw_routing_region`, `_draw_grove_region`) are inserted above the existing card grid in `draw_overview_right`. The nuke placard is a full-screen state machine keyed off `NAV.nuke_mode`.

**Tech Stack:** Python 3.11+, stdlib curses, psycopg2 (already present), soil.py (already present)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `grove_reader.py` | Postgres reads: agents, channels, messages, routing |
| Create | `tests/test_grove_reader.py` | Unit tests for grove_reader |
| Modify | `dashboard.py:630-660` | Add 3 fields to `SystemData.__init__` |
| Modify | `dashboard.py:686-720` | Add `fetch_grove()` after `fetch_postgres()` |
| Modify | `dashboard.py` (~line 885) | Add `background_refresh` call to `fetch_grove` |
| Modify | `dashboard.py:31-42` | Add color pair constants C_HASH_1..C_HASH_7 |
| Modify | `dashboard.py` (after init_colors) | Init hash color pairs in `main()` |
| Modify | `dashboard.py:1396-1483` | Add three region renderers + wire into `draw_overview_right` |
| Modify | `dashboard.py:1924+` | Add nuke placard state + `n` key handler |
| Modify | `dashboard.py:1264` | Update key strip hint |
| Modify | `tests/test_dashboard_ui.py` | Tests for new renderers + nuke placard |

---

### Task 1: grove_reader.py

**Files:**
- Create: `grove_reader.py`
- Test: `tests/test_grove_reader.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_grove_reader.py
"""Tests for grove_reader.py
b17: WDASH  ΔΣ=42
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import grove_reader


def _mock_conn(rows_by_query):
    """Build a mock psycopg2 connection whose cursor returns rows by call order."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    call_count = [0]
    def fetchall_side():
        i = call_count[0]
        call_count[0] += 1
        return rows_by_query[i] if i < len(rows_by_query) else []
    def fetchone_side():
        i = call_count[0]
        call_count[0] += 1
        rows = rows_by_query[i] if i < len(rows_by_query) else []
        return rows[0] if rows else None
    cur.fetchall.side_effect = fetchall_side
    cur.fetchone.side_effect = fetchone_side
    return conn


def test_grove_agents_returns_list():
    now = datetime.now(timezone.utc)
    rows = [("hanuman", now - timedelta(seconds=30)),
            ("heimdallr", now - timedelta(seconds=90))]
    conn = _mock_conn([rows])
    result = grove_reader.grove_agents(conn=conn)
    assert len(result) == 2
    assert result[0]["sender"] == "hanuman"
    assert result[0]["age_secs"] < 60
    assert result[1]["age_secs"] < 120


def test_grove_agents_empty():
    conn = _mock_conn([[]])
    result = grove_reader.grove_agents(conn=conn)
    assert result == []


def test_grove_channels_with_unread():
    channel_rows = [(1, "general"), (2, "architecture")]
    unread_general = [(0,)]
    unread_arch = [(3,)]
    conn = _mock_conn([channel_rows, unread_general, unread_arch])
    result = grove_reader.grove_channels(conn=conn, last_seen_ids={"architecture": 49})
    assert len(result) == 2
    names = {r["name"] for r in result}
    assert "general" in names
    assert "architecture" in names


def test_grove_channels_empty():
    conn = _mock_conn([[]])
    result = grove_reader.grove_channels(conn=conn)
    assert result == []


def test_routing_decisions_returns_empty_on_missing_table():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.execute.side_effect = Exception("relation does not exist")
    result = grove_reader.routing_decisions(conn=conn)
    assert result == []


def test_routing_decisions_returns_rows():
    now = datetime.now(timezone.utc)
    rows = [(now, "debug gleipnir", "ganesha", "rule-debug", 0.95, 3)]
    conn = _mock_conn([rows])
    result = grove_reader.routing_decisions(conn=conn)
    assert len(result) == 1
    assert result[0]["routed_to"] == "ganesha"
    assert result[0]["confidence"] == 0.95


def test_color_for_sender_stable():
    c1 = grove_reader.color_for_sender("hanuman")
    c2 = grove_reader.color_for_sender("hanuman")
    assert c1 == c2


def test_color_for_sender_different():
    colors = {grove_reader.color_for_sender(n) for n in
              ["hanuman", "heimdallr", "oakenscroll", "design-claude", "jeles"]}
    assert len(colors) > 1
```

- [x] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_grove_reader.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'grove_reader'`

- [x] **Step 3: Create grove_reader.py**

```python
"""grove_reader.py — Direct Postgres reader for Grove and routing data.
b17: WDASH  ΔΣ=42
"""
import os
from datetime import datetime, timezone

# ── Color hash palette (ANSI 16, maps to curses color pair numbers 11-17) ────
# Indices match the 7-color palette: cyan, magenta, yellow, green, blue, red, cyan+bold
_HASH_PAIRS = [11, 12, 13, 14, 15, 16, 17]


def color_for_sender(name: str) -> int:
    """Return a stable curses color_pair number for this sender name."""
    return _HASH_PAIRS[hash(name) % len(_HASH_PAIRS)]


def _pg_conn():
    import psycopg2
    dsn = os.environ.get("WILLOW_DB_URL", "")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        dbname=os.environ.get("WILLOW_PG_DB", "willow"),
        user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
    )


def grove_agents(conn=None) -> list[dict]:
    """Return agents with last_seen from grove.messages, most recent first.

    Each entry: {sender: str, last_seen_at: datetime, age_secs: int}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT sender, MAX(created_at) AS last_seen
            FROM grove.messages
            WHERE is_deleted = 0
            GROUP BY sender
            ORDER BY last_seen DESC
            LIMIT 20
        """)
        now = datetime.now(timezone.utc)
        rows = []
        for sender, last_seen in cur.fetchall():
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age_secs = int((now - last_seen).total_seconds())
            rows.append({"sender": sender, "last_seen_at": last_seen, "age_secs": age_secs})
        return rows
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def grove_channels(conn=None, last_seen_ids: dict | None = None) -> list[dict]:
    """Return channels with unread counts.

    last_seen_ids: {channel_name: last_seen_message_id}
    Each entry: {id: int, name: str, unread: int}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    last_seen_ids = last_seen_ids or {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name FROM grove.channels "
            "WHERE is_deleted = 0 OR is_deleted IS NULL ORDER BY id"
        )
        channels = cur.fetchall()
        result = []
        for ch_id, name in channels:
            last_id = last_seen_ids.get(name, 0)
            cur.execute(
                "SELECT COUNT(*) FROM grove.messages "
                "WHERE channel_id = %s AND id > %s AND is_deleted = 0",
                (ch_id, last_id),
            )
            row = cur.fetchone()
            unread = row[0] if row else 0
            result.append({"id": ch_id, "name": name, "unread": unread})
        return result
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def grove_messages(channel_name: str, conn=None, limit: int = 50,
                   since_id: int = 0) -> list[dict]:
    """Return messages for a channel, oldest first.

    Each entry: {id: int, sender: str, content: str, created_at: datetime}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM grove.channels WHERE name = %s LIMIT 1",
            (channel_name,),
        )
        row = cur.fetchone()
        if not row:
            return []
        ch_id = row[0]
        cur.execute(
            """
            SELECT id, sender, content, created_at
            FROM grove.messages
            WHERE channel_id = %s AND id > %s AND is_deleted = 0
            ORDER BY id DESC LIMIT %s
            """,
            (ch_id, since_id, limit),
        )
        msgs = []
        for mid, sender, content, created_at in cur.fetchall():
            msgs.append({"id": mid, "sender": sender,
                         "content": content, "created_at": created_at})
        return list(reversed(msgs))
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def routing_decisions(conn=None, limit: int = 8) -> list[dict]:
    """Return recent routing decisions. Returns [] if table not yet created.

    Each entry: {ts, prompt_snippet, routed_to, rule_matched, confidence, latency_ms}
    """
    close = conn is None
    if conn is None:
        conn = _pg_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ts, prompt_snippet, routed_to, rule_matched, confidence, latency_ms
            FROM willow.routing_decisions
            ORDER BY ts DESC LIMIT %s
            """,
            (limit,),
        )
        rows = []
        for ts, snippet, routed_to, rule_matched, confidence, latency_ms in cur.fetchall():
            rows.append({
                "ts": ts,
                "prompt_snippet": snippet,
                "routed_to": routed_to,
                "rule_matched": rule_matched,
                "confidence": float(confidence) if confidence is not None else 1.0,
                "latency_ms": latency_ms,
            })
        return rows
    except Exception:
        return []
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass
```

- [x] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_grove_reader.py -v
```
Expected: `7 passed`

- [x] **Step 5: Commit**

```bash
git add grove_reader.py tests/test_grove_reader.py
git commit -m "feat: grove_reader.py — Postgres reader for agents, channels, routing"
```

---

### Task 2: Extend SystemData with grove fields

**Files:**
- Modify: `dashboard.py:630-665` (`SystemData.__init__`)

- [x] **Step 1: Add three fields to SystemData**

In `dashboard.py`, find the `class SystemData:` block (around line 630). After `self._prev_cpu_stat`, add:

```python
        # Grove / orchestration
        self.grove_agents: list[dict]    = []   # from grove_reader.grove_agents()
        self.grove_channels: list[dict]  = []   # from grove_reader.grove_channels()
        self.routing_decisions: list[dict] = []  # from grove_reader.routing_decisions()
```

- [x] **Step 2: Run existing tests to verify nothing broke**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: `61 passed` (all existing tests still pass)

- [x] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: add grove_agents, grove_channels, routing_decisions to SystemData"
```

---

### Task 3: fetch_grove() + background integration

**Files:**
- Modify: `dashboard.py` — add `fetch_grove()` function and call it from `background_refresh`

- [x] **Step 1: Add fetch_grove() after fetch_postgres()**

Find `fetch_postgres()` in `dashboard.py` (around line 686). After its closing `except` block, add this new function:

```python
def fetch_grove():
    """Fetch Grove agents, channels, and routing decisions into DATA."""
    try:
        import grove_reader
        # Load channel cursors from SOIL so unread counts are accurate
        cursor_recs = soil.all_records("willow/dashboard/channel_cursors")
        last_seen_ids = {r["channel"]: r["last_seen_id"]
                         for r in cursor_recs if "channel" in r and "last_seen_id" in r}

        agents   = grove_reader.grove_agents()
        channels = grove_reader.grove_channels(last_seen_ids=last_seen_ids)
        routing  = grove_reader.routing_decisions()

        with DATA.lock:
            DATA.grove_agents      = agents
            DATA.grove_channels    = channels
            DATA.routing_decisions = routing
        DATA.push_log(f"grove: {len(agents)} agents · {len(channels)} channels")
    except Exception as ex:
        DATA.push_log(f"grove fetch error: {ex}")
```

- [x] **Step 2: Call fetch_grove from background_refresh**

Find `background_refresh` (search for `def background_refresh` — it's around line 1020). Add `fetch_grove()` to its loop alongside the other fetch calls:

```python
        fetch_grove()
```

Add it right after the `fetch_postgres()` call inside the loop.

- [x] **Step 3: Run existing tests**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: `61 passed`

- [x] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "feat: fetch_grove() populates DATA.grove_agents/channels/routing_decisions"
```

---

### Task 4: Hash color pairs init

**Files:**
- Modify: `dashboard.py:31-42` (color pair constants)
- Modify: `dashboard.py` main() color init section

- [x] **Step 1: Add C_HASH constants after existing color pair constants**

Find the `# ── Color pairs ──` block (around line 31). After `C_SELECT = 9`, add:

```python
# Sender/agent hash palette — 7 stable colors (pairs 11-17)
C_HASH_1 = 11  # cyan
C_HASH_2 = 12  # magenta
C_HASH_3 = 13  # yellow
C_HASH_4 = 14  # green  (bright via A_BOLD)
C_HASH_5 = 15  # blue   (bright via A_BOLD)
C_HASH_6 = 16  # red    (bright via A_BOLD)
C_HASH_7 = 17  # cyan   (bright via A_BOLD)
```

- [x] **Step 2: Initialize hash pairs in skins.init**

In `skins.py`, find the `init()` function. After the existing `curses.init_pair` calls, add:

```python
    # Sender hash palette
    curses.init_pair(11, curses.COLOR_CYAN,    -1)
    curses.init_pair(12, curses.COLOR_MAGENTA, -1)
    curses.init_pair(13, curses.COLOR_YELLOW,  -1)
    curses.init_pair(14, curses.COLOR_GREEN,   -1)
    curses.init_pair(15, curses.COLOR_BLUE,    -1)
    curses.init_pair(16, curses.COLOR_RED,     -1)
    curses.init_pair(17, curses.COLOR_CYAN,    -1)
```

- [x] **Step 3: Run tests**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: `61 passed`

- [x] **Step 4: Commit**

```bash
git add dashboard.py skins.py
git commit -m "feat: add C_HASH_1..7 color pairs for sender hash coloring"
```

---

### Task 5: Region renderer functions

**Files:**
- Modify: `dashboard.py` — add three region functions before `draw_overview_right`

- [x] **Step 1: Write tests for the renderers**

Add to `tests/test_dashboard_ui.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import curses
from unittest.mock import patch, MagicMock


def _make_win(h=20, w=40):
    """Return a mock curses window."""
    win = MagicMock()
    win.getmaxyx.return_value = (h, w)
    return win


def test_draw_agents_region_empty():
    import dashboard
    win = _make_win()
    y = dashboard._draw_agents_region(win, 0, 40, [])
    assert y > 0  # header row consumed at minimum


def test_draw_agents_region_shows_agents():
    import dashboard
    from datetime import datetime, timezone
    agents = [
        {"sender": "hanuman",    "age_secs": 30},
        {"sender": "heimdallr",  "age_secs": 200},
        {"sender": "oakenscroll","age_secs": 4000},  # gone, should be skipped
    ]
    win = _make_win()
    y = dashboard._draw_agents_region(win, 0, 40, agents)
    assert y >= 3  # header + 2 visible agents (gone skipped)


def test_draw_grove_region_empty():
    import dashboard
    win = _make_win()
    y = dashboard._draw_grove_region(win, 0, 40, [])
    assert y > 0


def test_draw_grove_region_shows_unread():
    import dashboard
    channels = [
        {"name": "general",      "unread": 0},
        {"name": "architecture", "unread": 3},
    ]
    win = _make_win()
    y = dashboard._draw_grove_region(win, 0, 40, channels)
    assert y >= 3  # header + 2 channels


def test_draw_routing_region_empty():
    import dashboard
    win = _make_win()
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
    y = dashboard._draw_routing_region(win, 0, 40, decisions)
    assert y >= 2  # header + 1 row
```

- [x] **Step 2: Run tests to confirm they fail (ImportError on missing functions)**

```bash
python3 -m pytest tests/test_dashboard_ui.py -v 2>&1 | tail -15
```
Expected: failures with `AttributeError: module 'dashboard' has no attribute '_draw_agents_region'`

- [x] **Step 3: Add _fmt_age helper**

In `dashboard.py`, after the `_fmt()` helper (around line 668), add:

```python
def _fmt_age(secs: int) -> str:
    """Return a compact age string: '30s', '5m', '2h'."""
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"
```

- [x] **Step 4: Add three region renderer functions**

In `dashboard.py`, find the line `def draw_overview_right(win):` (around line 1396). Insert these three functions **immediately before** it:

```python
def _draw_agents_region(win, y: int, w: int, agents: list) -> int:
    """Draw AGENTS region. Returns next y after region."""
    import grove_reader as _gr
    _section_header(win, y, "AGENTS"); y += 1
    visible = [a for a in agents if a.get("age_secs", 9999) < 3600]
    if not visible:
        safe_addstr(win, y, 2, "no active agents", curses.color_pair(C_DIM))
        return y + 1
    for agent in visible[:4]:
        sender   = agent["sender"]
        age_secs = agent.get("age_secs", 0)
        if age_secs < 120:
            state, state_col = "running", C_GREEN
        elif age_secs < 900:
            state, state_col = "idle   ", C_DIM
        else:
            state, state_col = "stale  ", C_DIM
        age_str  = _fmt_age(age_secs)
        col      = curses.color_pair(_gr.color_for_sender(sender))
        name_w   = max(1, w - 20)
        safe_addstr(win, y, 2, sender[:name_w], col)
        safe_addstr(win, y, 2 + name_w, f" {state} {age_str:>4}",
                    curses.color_pair(state_col))
        y += 1
    return y


def _draw_routing_region(win, y: int, w: int, decisions: list) -> int:
    """Draw ROUTING region. Returns next y after region."""
    import grove_reader as _gr
    _section_header(win, y, "ROUTING"); y += 1
    if not decisions:
        safe_addstr(win, y, 2, "no routing decisions yet this session",
                    curses.color_pair(C_DIM))
        return y + 1
    for d in decisions[:6]:
        ts = d.get("ts")
        ts_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[:5]
        snippet = (d.get("prompt_snippet") or "")[:35]
        target  = d.get("routed_to") or "?"
        conf    = d.get("confidence", 1.0)
        col     = curses.color_pair(_gr.color_for_sender(target))
        dim     = curses.A_DIM if conf < 0.7 else 0
        line    = f"{ts_str}  \"{snippet}\"  → {target}"
        safe_addstr(win, y, 2, line[:w - 3], col | dim)
        y += 1
    return y


def _draw_grove_region(win, y: int, w: int, channels: list) -> int:
    """Draw GROVE region. Returns next y after region."""
    _section_header(win, y, "GROVE"); y += 1
    if not channels:
        safe_addstr(win, y, 2, "grove: not connected", curses.color_pair(C_DIM))
        return y + 1
    _FIXED_ORDER = ["general", "architecture", "handoffs", "readme"]
    ordered = sorted(channels, key=lambda c: (
        _FIXED_ORDER.index(c["name"]) if c["name"] in _FIXED_ORDER else len(_FIXED_ORDER),
        c["name"],
    ))
    for ch in ordered:
        name   = ch["name"]
        unread = ch.get("unread", 0)
        if unread > 0:
            glyph, glyph_col = "•", C_AMBER   # bullet •
            suffix = f" {unread}"
        else:
            glyph, glyph_col = "·", C_DIM     # middle dot ·
            suffix = ""
        safe_addstr(win, y, 2, f"#{name}", curses.color_pair(C_BLUE))
        x_g = 2 + 1 + len(name) + 2
        if x_g < w - 4:
            safe_addstr(win, y, x_g, glyph + suffix, curses.color_pair(glyph_col))
        y += 1
    return y
```

- [x] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_dashboard_ui.py -v
```
Expected: all new tests pass (existing tests remain passing)

- [x] **Step 6: Commit**

```bash
git add dashboard.py tests/test_dashboard_ui.py
git commit -m "feat: _draw_agents_region, _draw_routing_region, _draw_grove_region renderers"
```

---

### Task 6: Wire regions into draw_overview_right

**Files:**
- Modify: `dashboard.py:1396-1483` (`draw_overview_right`)

- [x] **Step 1: Replace the body of draw_overview_right**

Find `draw_overview_right(win)` in `dashboard.py` (line 1396). The section between the expanded-card early return (line 1428) and `draw_panel_border` (line 1482) is what we're extending.

Replace the section from `# ── Compact STATUS strip` through `# ── Card grid fills remaining space ───` with:

```python
    # ── Region 1: VITALS strip (unchanged) ───────────────────────────────────
    y = 0
    _section_header(win, y, "STATUS"); y += 1

    try:
        kp_warn = int(kp) > 0
    except (ValueError, TypeError):
        kp_warn = False
    try:
        safe_ok = int(safe_p) == int(safe_t) and int(safe_t) > 0
    except (ValueError, TypeError):
        safe_ok = False

    rows_vitals = [
        ("●", "Postgres", f"{pg_kb} {pg_edges}e", C_GREEN),
        ("▲" if kp_warn else "●", "Kart",
         f"{kp}q {kr}r", C_AMBER if kp_warn else C_GREEN),
        ("●" if ollama_up else "✗", "Ollama",
         f"{ygg}", C_GREEN if ollama_up else C_RED),
        ("●" if safe_ok else "▲", "SAFE",
         f"{safe_p}/{safe_t}", C_GREEN if safe_ok else C_AMBER),
    ]
    for dot, name, metric, col in rows_vitals:
        name_w = max(1, w - len(dot) - len(metric) - 4)
        line = f"{dot} {name:<{name_w}}{metric}"
        safe_addstr(win, y, 1, line[:w - 2], curses.color_pair(col)); y += 1

    bar_w = max(4, (w - 16) // 2)
    cpu_bar = _ascii_bar(cpu, bar_w)
    bar_col = C_AMBER if cpu > 85 else C_GREEN
    tmp_col = C_AMBER if tmp > 70 else C_DIM
    safe_addstr(win, y, 1, "CPU ", curses.color_pair(C_DIM))
    safe_addstr(win, y, 5, cpu_bar, curses.color_pair(bar_col))
    safe_addstr(win, y, 5 + bar_w, f" {cpu:2d}%", curses.color_pair(C_DIM))
    safe_addstr(win, y, 5 + bar_w + 4, f"  TMP {tmp}°C", curses.color_pair(tmp_col))
    y += 1

    # ── Regions 2-4: AGENTS / ROUTING / GROVE ────────────────────────────────
    with DATA.lock:
        agents    = list(DATA.grove_agents)
        channels  = list(DATA.grove_channels)
        routing   = list(DATA.routing_decisions)

    remaining = h - y - 4   # reserve 4 rows for card section
    if remaining >= 3:
        y = _draw_agents_region(win, y, w, agents)
    if remaining >= 6:
        y = _draw_routing_region(win, y, w, routing)
    if remaining >= 3:
        y = _draw_grove_region(win, y, w, channels)

    # ── Region 5: CARD grid fills remaining space ─────────────────────────────
    cards_y = y
    cards_h = h - cards_y
    if cards_h >= 4 and _CARDS:
        _section_header(win, cards_y, "CARDS"); cards_y += 1; cards_h -= 1
        if cards_h >= 3:
            try:
                sub = win.derwin(cards_h, w, cards_y, 0)
                NAV.card_scroll = card_mod.draw_card_grid(
                    sub, _CARDS, NAV.card_idx, NAV.card_scroll)
                sub.noutrefresh()
            except curses.error:
                pass
```

- [x] **Step 2: Run all tests**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: `61 passed` + new tests (≥67 total)

- [x] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: wire AGENTS/ROUTING/GROVE regions into draw_overview_right"
```

---

### Task 7: Nuke placard + n key

**Files:**
- Modify: `dashboard.py` — add nuke placard + state to NAV + key handler

- [x] **Step 1: Write nuke placard tests**

Add to `tests/test_dashboard_ui.py`:

```python
def test_nuke_placard_renders_without_crash():
    import dashboard
    stdscr = _make_win(h=30, w=80)
    stdscr.getmaxyx.return_value = (30, 80)
    # Should not raise
    dashboard.draw_nuke_placard(stdscr, "")


def test_nuke_placard_with_partial_input():
    import dashboard
    stdscr = _make_win(h=30, w=80)
    stdscr.getmaxyx.return_value = (30, 80)
    dashboard.draw_nuke_placard(stdscr, "I UND")
```

- [x] **Step 2: Run to confirm they fail**

```bash
python3 -m pytest tests/test_dashboard_ui.py::test_nuke_placard_renders_without_crash -v
```
Expected: `AttributeError: module 'dashboard' has no attribute 'draw_nuke_placard'`

- [x] **Step 3: Add nuke_mode fields to NavState**

Find `class NavState:` in `dashboard.py`. Add two fields in `__init__`:

```python
        self.nuke_mode  = False   # True when nuke placard is active
        self.nuke_input = ""      # characters typed toward "I UNDERSTAND"
```

- [x] **Step 4: Add draw_nuke_placard function**

Add this function just before `def main(stdscr):` (around line 1897):

```python
_NUKE_PLACARD_LINES = [
    "",
    "╔" + "═" * 71 + "╗",
    "║" + " " * 71 + "║",
    "║" + "                        ▲  IRREVERSIBLE ACTION  ▲                       ║",
    "║" + " " * 71 + "║",
    "╠" + "═" * 71 + "╣",
    "║" + " " * 71 + "║",
    "║  WHAT WILL BE DESTROYED" + " " * 46 + "║",
    "║  ───────────────────────" + " " * 48 + "║",
    "║    • All atoms in ~/.willow/store/" + " " * 38 + "║",
    "║    • All sessions in willow.sap_sessions" + " " * 31 + "║",
    "║    • All LOAM atoms in willow_19" + " " * 39 + "║",
    "║    • FRANK's ledger chain from genesis" + " " * 35 + "║",
    "║    • Grove messages in this database" + " " * 37 + "║",
    "║" + " " * 71 + "║",
    "║  WHAT WILL BE PRESERVED" + " " * 46 + "║",
    "║  ──────────────────────" + " " * 49 + "║",
    "║    • Your SSH keys" + " " * 56 + "║",
    "║    • Your GPG keys" + " " * 56 + "║",
    "║    • Your Postgres cluster (only the willow_19 database is dropped)" + "   ║",
    "║    • Files outside ~/.willow/" + " " * 44 + "║",
    "║" + " " * 71 + "║",
    "║  There is no undo. There is no recovery. There is no backup this      ║",
    "║  script is quietly keeping for you." + " " * 34 + "║",
    "║" + " " * 71 + "║",
    "║  To proceed, type:   I UNDERSTAND" + " " * 35 + "║",
    "║  To abort, press:    Esc" + " " * 44 + "║",
    "║" + " " * 71 + "║",
    # Input line is rendered dynamically
    "║" + " " * 71 + "║",
    "╚" + "═" * 71 + "╝",
    "",
]


def draw_nuke_placard(stdscr, input_so_far: str) -> None:
    """Full-screen nuke confirmation placard. No modal — takes the whole screen."""
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    lines = list(_NUKE_PLACARD_LINES)
    # Inject input into the "> _" row (second-to-last non-empty line)
    input_line = f"║  > {input_so_far}_" + " " * max(0, 65 - len(input_so_far)) + "║"
    lines[-3] = input_line
    start_y = max(0, (h - len(lines)) // 2)
    for i, line in enumerate(lines):
        y = start_y + i
        if y >= h:
            break
        x = max(0, (w - 73) // 2)
        try:
            stdscr.addstr(y, x, line[:w - x], curses.color_pair(C_RED))
        except curses.error:
            pass
    stdscr.noutrefresh()
    curses.doupdate()
```

- [x] **Step 5: Add n key handler to the main loop**

In `dashboard.py`, find the main event loop (around line 1924). Find the section handling the `q` quit key (search for `NAV.quit_confirm`). Above that block, add nuke placard handling:

```python
            # ── Nuke placard mode ──────────────────────────────────────────
            if NAV.nuke_mode:
                if key == 27:                        # Esc — abort
                    NAV.nuke_mode  = False
                    NAV.nuke_input = ""
                elif key in (curses.KEY_BACKSPACE, 127):
                    NAV.nuke_input = NAV.nuke_input[:-1]
                elif 32 <= key <= 126:
                    NAV.nuke_input += chr(key)
                    if NAV.nuke_input == "I UNDERSTAND":
                        # Confirmed — for now just log and reset (actual nuke in future plan)
                        DATA.push_log("nuke: confirmed — not implemented yet")
                        NAV.nuke_mode  = False
                        NAV.nuke_input = ""
                draw_nuke_placard(stdscr, NAV.nuke_input)
                continue

```

Also add the `n` key trigger in the global key section (near `ord('r')` for refresh). Find the block handling `elif key == ord('r'):` and add after it:

```python
                elif key == ord('n') and not NAV.nuke_mode:
                    NAV.nuke_mode  = True
                    NAV.nuke_input = ""
                    continue
```

- [x] **Step 6: Run all tests**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all tests pass (61 + new ≥ 69 total)

- [x] **Step 7: Commit**

```bash
git add dashboard.py tests/test_dashboard_ui.py
git commit -m "feat: nuke placard — n triggers full-screen confirmation, I UNDERSTAND to proceed"
```

---

### Task 8: Key strip hint update + terminal size check

**Files:**
- Modify: `dashboard.py:1264` (`draw_page_bar`)
- Modify: `dashboard.py:2132` (terminal size check)

- [x] **Step 1: Update key strip hint**

Find `draw_page_bar` (around line 1240). Update the hint string:

Old:
```python
        hint = " Tab=focus ←→=page Enter=expand Esc=back qq=quit "
```

New:
```python
        hint = " Tab=focus ←→=page Enter=expand Esc=back n=nuke qq=quit "
```

- [x] **Step 2: Update terminal size message**

Find the terminal-too-small check (around line 2132):

Old:
```python
                try: stdscr.addstr(0, 0, "Terminal too small")
```

New:
```python
                try: stdscr.addstr(0, 0, "terminal too small — resize to 80×24 or larger")
```

- [x] **Step 3: Run all tests**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all tests pass

- [x] **Step 4: Final commit**

```bash
git add dashboard.py
git commit -m "feat: key strip adds n=nuke hint; terminal-too-small message updated"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| §3 Terminal-native, unapologetic | No changes — existing design holds |
| §3 Always-visible over on-demand | Task 6 wires all 4 regions |
| §3 Destroyed-first, preserved-second | Task 7 placard lists destroyed first |
| §4.1 VITALS strip extended | Task 6 (kept as-is, section header renamed STATUS→VITALS possible post-ratification) |
| §4.2 AGENTS region | Tasks 1, 5, 6 |
| §4.3 ROUTING region (stub) | Tasks 1, 5, 6 — stub returns [] until willow_route ships |
| §4.4 GROVE region | Tasks 1, 5, 6 |
| §4.5 CARD WORKSPACE | Unchanged |
| §4.6 KEY STRIP adds n nuke | Task 8 |
| §5 ANSI 16 only | All new code uses existing C_* pairs + C_HASH pairs (16-color base) |
| §6 n=nuke keyboard | Tasks 7, 8 |
| §8 Reactor-door placard | Task 7 |
| §8 I UNDERSTAND confirm phrase | Task 7 |
| §10 Acceptance checklist item 5 (n triggers placard) | Task 7 |
| §10 Acceptance checklist item 6 (I UNDERSTAND exactly) | Task 7 |
| §10 Acceptance checklist item 7 (Esc returns to previous) | Task 7 |
| §10 Acceptance checklist item 8 (ANSI 16 only) | Task 4, all renderers |
| §10 Acceptance checklist item 9 (no new dependencies) | All code is stdlib + existing deps |
| §10 Acceptance checklist item 10 (80×24 min) | Task 8 |

**Out of scope for this plan (needs willow_route Plan 4):**
- §4.3 ROUTING with live data — stub returns [] until `willow.routing_decisions` table exists
- `willow.sap_sessions.last_seen_at` — agent heartbeat falls back to grove.messages aggregation only
- `§10` checklist items 1-4 — timing/perf tests require manual verification

**Placeholder scan:** None found.

**Type consistency:** `color_for_sender` defined in Task 1 (grove_reader.py), imported as `_gr.color_for_sender` in Task 5 renderers. `_fmt_age` defined in Task 5 Step 3, used in Task 5 Step 4. Consistent throughout.
