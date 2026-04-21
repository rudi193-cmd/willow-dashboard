"""cards.py — Card definitions, grid renderer, and expanded view for Willow Dashboard.
b17: WDASH  ΔΣ=42
"""
import curses
import json
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional
import soil
import skins

# ── Card dataclass ────────────────────────────────────────────────────────────

@dataclass
class CardDef:
    id: str
    label: str
    category: str = "system"          # system | work | dev | personal
    built_in: bool = False
    enabled: bool = True
    order: int = 99

    # Grid display queries (SQLite or Postgres)
    value_query: str = ""             # single value shown large
    sub_query: str = ""               # single value shown as subtitle
    sub_format: str = "{}"            # "{} tasks" — {} replaced by sub_query result
    state_query: str = ""             # returns "green"|"amber"|"red"|"blue"

    # Data source (one of):
    soil_collection: str = ""
    pg_table: str = ""

    # Expanded view
    expand_query: str = ""
    expand_columns: list = field(default_factory=list)

    # Actions shown when expanded
    actions: list = field(default_factory=list)  # [{key, label, type}]

    refresh_interval: int = 60
    skin_override: Optional[dict] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, d: dict) -> "CardDef":
        valid = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in valid})


# ── Seed catalog ──────────────────────────────────────────────────────────────

CARD_SEEDS: list[CardDef] = [
    # ── Built-in system cards (always enabled) ────────────────────────────────
    CardDef(
        id="kart", label="Kart Queue", category="system", built_in=True,
        order=0, enabled=True,
        pg_table="public.kart_task_queue",
        value_query="SELECT COUNT(*) FROM public.kart_task_queue WHERE status='pending'",
        sub_query="SELECT COUNT(*) FROM public.kart_task_queue WHERE status='running'",
        sub_format="{} running",
        state_query=(
            "SELECT CASE WHEN COUNT(*)>10 THEN 'amber' "
            "WHEN COUNT(*)>0 THEN 'green' ELSE 'dim' END "
            "FROM public.kart_task_queue WHERE status='pending'"
        ),
        expand_query="SELECT task_id,task,status,created_at FROM public.kart_task_queue ORDER BY created_at DESC LIMIT 50",
        expand_columns=["task_id", "task", "status", "created_at"],
        actions=[
            {"key": "c", "label": "cancel task", "type": "confirm"},
            {"key": "r", "label": "retry task",  "type": "confirm"},
        ],
    ),
    CardDef(
        id="knowledge", label="Knowledge", category="system", built_in=True,
        order=1, enabled=True,
        pg_table="public.knowledge",
        value_query="SELECT COUNT(*) FROM public.knowledge",
        sub_query="SELECT COUNT(*) FROM public.knowledge WHERE created_at::timestamp > NOW() - INTERVAL '24 hours'",
        sub_format="{} today",
        state_query="SELECT 'blue'",
        expand_query="SELECT id,title,category,created_at FROM public.knowledge ORDER BY created_at DESC LIMIT 50",
        expand_columns=["id", "title", "category", "created_at"],
        actions=[
            {"key": "/", "label": "search knowledge", "type": "chat"},
        ],
    ),
    CardDef(
        id="yggdrasil", label="Yggdrasil", category="system", built_in=True,
        order=2, enabled=True,
        value_query="",  # populated at runtime via Ollama API
        state_query="",
        actions=[
            {"key": "p", "label": "pull new version", "type": "chat"},
        ],
    ),
    CardDef(
        id="agents", label="Agents", category="system", built_in=True,
        order=3, enabled=True,
        # populated at runtime from agents.json / registry; no DB query needed
        value_query="", sub_query="", state_query="",
        expand_columns=["name", "role"],
        actions=[
            {"key": "v", "label": "view detail", "type": "chat"},
        ],
    ),
    CardDef(
        id="secrets", label="Secrets Vault", category="system", built_in=True,
        order=4, enabled=True,
        value_query="",  # populated at runtime via vault file
        state_query="",
        actions=[
            {"key": "r", "label": "reveal secret", "type": "confirm"},
        ],
    ),
    CardDef(
        id="fleet", label="Fleet", category="system", built_in=True,
        order=5, enabled=True,
        value_query="",  # populated at runtime via credentials ping
        state_query="",
        actions=[
            {"key": "p", "label": "ping provider",  "type": "confirm"},
            {"key": "u", "label": "update key",     "type": "chat"},
        ],
    ),
    CardDef(
        id="mcp", label="MCP Servers", category="system", built_in=True,
        order=6, enabled=True,
        value_query="",  # populated at runtime via .mcp.json scan
        state_query="",
        actions=[
            {"key": "l", "label": "list tools",    "type": "chat"},
            {"key": "s", "label": "show auth",     "type": "chat"},
        ],
    ),

    # ── Optional catalog (seeded disabled) ────────────────────────────────────
    CardDef(id="projects",  label="Projects",     category="work",     built_in=False, enabled=False, order=10,
            soil_collection="projects/items",
            value_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='active' AND deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.due_date') < date('now') AND deleted=0",
            sub_format="{} overdue", state_query="SELECT CASE WHEN (SELECT COUNT(*) FROM records WHERE json_extract(data,'$.due_date') < date('now') AND deleted=0)>0 THEN 'amber' ELSE 'green' END",
            expand_columns=["name","status","due_date"],
            actions=[{"key":"a","label":"add project","type":"chat"},{"key":"u","label":"update status","type":"chat"},{"key":"x","label":"archive","type":"confirm"}]),
    CardDef(id="job-hunt",  label="Job Hunt",     category="work",     built_in=False, enabled=False, order=11,
            soil_collection="job-hunt/applications",
            value_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='applied' AND deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='interview' AND deleted=0",
            sub_format="{} interviews", state_query="SELECT 'blue'",
            expand_columns=["company","role","status","applied_date"],
            actions=[{"key":"a","label":"add application","type":"chat"},{"key":"u","label":"update status","type":"chat"}]),
    CardDef(id="notes",     label="Notes",        category="work",     built_in=False, enabled=False, order=12,
            soil_collection="notes/entries",
            value_query="SELECT COUNT(*) FROM records WHERE deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE date(json_extract(data,'$.created_at'))=date('now') AND deleted=0",
            sub_format="{} today", state_query="SELECT 'dim'",
            expand_columns=["title","created_at"],
            actions=[{"key":"a","label":"quick-add note","type":"chat"}]),
    CardDef(id="journal",   label="Journal",      category="personal", built_in=False, enabled=False, order=13,
            soil_collection="journal/entries",
            value_query="SELECT COUNT(*) FROM records WHERE date(json_extract(data,'$.date'))=date('now') AND deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE deleted=0",
            sub_format="{} total", state_query="SELECT CASE WHEN (SELECT COUNT(*) FROM records WHERE date(json_extract(data,'$.date'))=date('now') AND deleted=0)>0 THEN 'green' ELSE 'amber' END",
            expand_columns=["date","snippet"],
            actions=[{"key":"a","label":"append entry","type":"chat"}]),
    CardDef(id="goals",     label="Goals",        category="personal", built_in=False, enabled=False, order=14,
            soil_collection="goals/items",
            value_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='active' AND deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='done' AND deleted=0",
            sub_format="{} done", state_query="SELECT 'green'",
            expand_columns=["title","status","progress"],
            actions=[{"key":"c","label":"check off item","type":"confirm"}]),
    CardDef(id="git-status",label="Git Status",   category="dev",      built_in=False, enabled=False, order=15,
            value_query="", state_query="",  # runtime only — reads git subprocess
            expand_columns=["file","change"],
            actions=[{"key":"l","label":"view log","type":"chat"}]),
    CardDef(id="open-prs",  label="Open PRs",     category="dev",      built_in=False, enabled=False, order=16,
            value_query="", state_query="",  # runtime only — reads GitHub API
            expand_columns=["repo","title","status"],
            actions=[{"key":"v","label":"view list","type":"chat"}]),
    CardDef(id="build",     label="Build / CI",   category="dev",      built_in=False, enabled=False, order=17,
            value_query="", state_query="",
            expand_columns=["job","status","finished_at"],
            actions=[{"key":"v","label":"view log","type":"chat"}]),
    CardDef(id="todos",     label="TODOs",        category="dev",      built_in=False, enabled=False, order=18,
            value_query="", state_query="",  # runtime — grep codebase
            expand_columns=["file","line","text"],
            actions=[]),
    CardDef(id="calendar",  label="Calendar",     category="personal", built_in=False, enabled=False, order=19,
            value_query="", state_query="",
            expand_columns=["time","title","location"],
            actions=[{"key":"v","label":"view today","type":"chat"}]),
    CardDef(id="habits",    label="Habits",       category="personal", built_in=False, enabled=False, order=20,
            soil_collection="habits/items",
            value_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.streak')>0 AND deleted=0",
            sub_query="SELECT MAX(json_extract(data,'$.streak')) FROM records WHERE deleted=0",
            sub_format="{} best streak", state_query="SELECT 'green'",
            expand_columns=["name","streak","last_done"],
            actions=[{"key":"c","label":"check off today","type":"confirm"}]),
    CardDef(id="reading",   label="Reading List", category="personal", built_in=False, enabled=False, order=21,
            soil_collection="reading/items",
            value_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='reading' AND deleted=0",
            sub_query="SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='queue' AND deleted=0",
            sub_format="{} queued", state_query="SELECT 'blue'",
            expand_columns=["title","author","status"],
            actions=[{"key":"f","label":"mark finished","type":"confirm"},{"key":"a","label":"add book","type":"chat"}]),
]

_CARD_MAP: dict[str, CardDef] = {c.id: c for c in CARD_SEEDS}


# ── SOIL seed / load ──────────────────────────────────────────────────────────

def seed_cards() -> None:
    """Seed card definitions to SOIL. Built-in cards always overwrite so query
    fixes in code propagate on next restart. User cards are insert-only."""
    existing = {r["id"] for r in soil.all_records("willow-dashboard/cards")}
    for c in CARD_SEEDS:
        if c.built_in or c.id not in existing:
            soil.put("willow-dashboard/cards", c.id, c.to_dict())


def load_cards() -> list[CardDef]:
    """Load enabled cards from SOIL, sorted by order."""
    recs = soil.all_records("willow-dashboard/cards")
    cards = []
    for r in recs:
        try:
            c = CardDef.from_dict(r)
            if c.enabled:
                cards.append(c)
        except Exception:
            pass
    cards.sort(key=lambda c: c.order)
    return cards


def save_card(card: CardDef) -> None:
    """Persist a card definition to SOIL."""
    soil.put("willow-dashboard/cards", card.id, card.to_dict())


# ── Value cache — populated by background thread, read by draw ───────────────
# {card_id: {"value": str, "sub": str, "state": str, "rows": list[dict]}}
_VALUE_CACHE: dict[str, dict] = {}
_CACHE_LOCK = __import__("threading").Lock()


def cache_put(card_id: str, value: str, sub: str, state: str) -> None:
    with _CACHE_LOCK:
        existing = _VALUE_CACHE.get(card_id, {})
        _VALUE_CACHE[card_id] = {
            "value": value, "sub": sub, "state": state,
            "rows": existing.get("rows", []),
        }


def cache_put_rows(card_id: str, rows: list, columns: list) -> None:
    """Store expand rows for cards whose data comes from fetch functions."""
    with _CACHE_LOCK:
        existing = _VALUE_CACHE.get(card_id, {"value": "—", "sub": "", "state": ""})
        existing["rows"] = rows
        existing["columns"] = columns
        _VALUE_CACHE[card_id] = existing


def cache_get(card_id: str) -> dict:
    with _CACHE_LOCK:
        return _VALUE_CACHE.get(card_id, {"value": "—", "sub": "", "state": "", "rows": []})


def refresh_card_values(cards: list) -> None:
    """Run value/sub/state queries for all cards and store in cache.
    Skips cards with no queries — those are populated by dedicated fetch
    functions in dashboard.py (yggdrasil, fleet, secrets, agents, mcp).
    Called from background thread — safe to block on I/O.
    """
    for card in cards:
        if not card.value_query and not card.sub_query and not card.state_query:
            continue
        try:
            value = _run_card_query(card, card.value_query)
            sub   = _run_card_query(card, card.sub_query)
            state = _run_card_query(card, card.state_query)
            cache_put(card.id, value or "—", sub or "", state or "")
        except Exception:
            cache_put(card.id, "?", "", "red")


# ── Runtime data helpers ──────────────────────────────────────────────────────

def _run_soil_query(card: CardDef, sql: str) -> str:
    """Run a SQLite query against the card's soil_collection."""
    if not card.soil_collection or not sql:
        return ""
    row = soil.query_one(card.soil_collection, sql)
    return str(row[0]) if row and row[0] is not None else "0"


def _pg_conn():
    """Open a Postgres connection the same way the dashboard does."""
    import psycopg2
    dsn = os.environ.get("WILLOW_DB_URL", "")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        dbname=os.environ.get("WILLOW_PG_DB", "willow"),
        user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
    )


def _run_pg_query(card: CardDef, sql: str) -> str:
    """Run a Postgres query against the card's pg_table context."""
    if not sql:
        return ""
    try:
        conn = _pg_conn()
        cur  = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        conn.close()
        return str(row[0]) if row and row[0] is not None else "0"
    except Exception as e:
        return f"!{type(e).__name__}"


def _run_card_query(card: CardDef, sql: str) -> str:
    """Run value_query / sub_query / state_query for a card."""
    if not sql:
        return ""
    if card.pg_table:
        return _run_pg_query(card, sql)
    if card.soil_collection:
        return _run_soil_query(card, sql)
    return ""


def _run_expand_query(card: CardDef) -> tuple[list[dict], list[str]]:
    """Return (rows, columns) for the expanded view.
    If no SQL query, falls back to rows cached by a fetch function.
    """
    if card.expand_query and card.expand_columns:
        try:
            if card.pg_table:
                conn = _pg_conn()
                cur  = conn.cursor()
                cur.execute(card.expand_query)
                rows = cur.fetchall()
                conn.close()
            elif card.soil_collection:
                rows = soil.query(card.soil_collection, card.expand_query)
            else:
                rows = []
            cols = card.expand_columns
            return [{cols[i]: row[i] for i in range(min(len(cols), len(row)))} for row in rows], cols
        except Exception:
            pass
    # Fall back to rows stored by fetch functions
    cached = cache_get(card.id)
    cols   = cached.get("columns", card.expand_columns or [])
    return cached.get("rows", []), cols


def _state_to_color(state: str) -> int:
    """Map state string to curses color pair attr."""
    return {
        "green": curses.color_pair(skins.C_GREEN),
        "amber": curses.color_pair(skins.C_AMBER),
        "red":   curses.color_pair(skins.C_RED),
        "blue":  curses.color_pair(skins.C_BLUE),
    }.get(state, curses.color_pair(skins.C_DIM))


# ── Card grid renderer ────────────────────────────────────────────────────────

def draw_card_grid(win, cards: list[CardDef], selected: int, scroll_top: int) -> int:
    """Draw the card grid into `win`. Returns the new scroll_top after clamping.

    Layout uses skin.grid_columns and skin.card_height.
    selected is absolute index into cards list.
    scroll_top is first visible row index (0-based).
    """
    skin = skins.ACTIVE
    h, w = win.getmaxyx()
    cols = skin.grid_columns
    card_h = skin.card_height
    card_w = max(4, w // cols)

    visible_rows = max(1, (h - 2) // card_h)   # -2 for top margin + bottom strip
    total_rows = (len(cards) + cols - 1) // cols

    # Clamp scroll so selected card row is in view
    sel_row = selected // cols
    if sel_row < scroll_top:
        scroll_top = sel_row
    elif sel_row >= scroll_top + visible_rows:
        scroll_top = sel_row - visible_rows + 1
    scroll_top = max(0, min(scroll_top, max(0, total_rows - visible_rows)))

    win.erase()

    for vis_row in range(visible_rows):
        abs_row = scroll_top + vis_row
        for col in range(cols):
            idx = abs_row * cols + col
            if idx >= len(cards):
                break
            card = cards[idx]
            cy = vis_row * card_h + 1
            cx = col * card_w
            is_selected = (idx == selected)
            _draw_card_cell(win, card, cy, cx, card_w, card_h, is_selected)

    # + card at end (for creation)
    plus_idx = len(cards)
    plus_row = plus_idx // cols - scroll_top
    plus_col = plus_idx % cols
    if 0 <= plus_row < visible_rows:
        _draw_plus_card(win, 1 + plus_row * card_h, plus_col * card_w, card_w, card_h,
                        is_selected=(selected == plus_idx))

    # Scroll indicator + symbol key
    if total_rows > visible_rows:
        first_card = scroll_top * cols + 1
        last_card = min((scroll_top + visible_rows) * cols, len(cards))
        indicator = f"{first_card}-{last_card} / {len(cards)}"
        try:
            win.addstr(h - 1, 1, indicator, curses.color_pair(skins.C_DIM))
        except curses.error:
            pass

    if skin.accessible:
        try:
            win.addstr(h - 1, w - len(skins.SYMBOL_KEY) - 1, skins.SYMBOL_KEY,
                       curses.color_pair(skins.C_DIM))
        except curses.error:
            pass

    return scroll_top


def _draw_card_cell(win, card: CardDef, y: int, x: int, w: int, h: int, selected: bool) -> None:
    """Render one card cell in the grid."""
    skin = skins.ACTIVE
    h_max, w_max = win.getmaxyx()

    border_attr = curses.color_pair(skins.C_SELECT) if selected else curses.color_pair(skins.C_DIM)

    # Border
    try:
        win.attron(border_attr)
        win.addstr(y,     x,     "┌" + "─" * (w - 2) + "┐")
        win.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘")
        for row in range(1, h - 1):
            if y + row < h_max:
                win.addstr(y + row, x, "│")
                win.addstr(y + row, x + w - 1, "│")
        win.attroff(border_attr)
    except curses.error:
        pass

    # Label
    label = card.label[:w - 4]
    try:
        win.addstr(y + 1, x + 2, label, curses.color_pair(skins.C_HEADER) | curses.A_BOLD)
    except curses.error:
        pass

    # Value — read from background cache, never block the draw thread
    cached   = cache_get(card.id)
    value    = cached["value"]
    sub      = cached["sub"]
    state    = cached["state"]
    val_attr = _state_to_color(state)

    if skin.accessible and state in skins.STATE_SYMBOLS:
        value = skins.STATE_SYMBOLS[state] + " " + value

    try:
        win.addstr(y + 2, x + 2, value[:w - 4], val_attr | curses.A_BOLD)
    except curses.error:
        pass

    # Sub-label
    if h > 3 and sub:
        sub_text = card.sub_format.replace("{}", sub)[:w - 4]
        try:
            win.addstr(y + 3, x + 2, sub_text, curses.color_pair(skins.C_DIM))
        except curses.error:
            pass


def _draw_plus_card(win, y: int, x: int, w: int, h: int, is_selected: bool) -> None:
    """Draw the + card that triggers card creation."""
    border_attr = curses.color_pair(skins.C_SELECT) if is_selected else curses.color_pair(skins.C_DIM)
    h_max, _ = win.getmaxyx()
    try:
        win.attron(border_attr)
        win.addstr(y, x, "┌" + "─" * (w - 2) + "┐")
        win.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘")
        for row in range(1, h - 1):
            if y + row < h_max:
                win.addstr(y + row, x, "│")
                win.addstr(y + row, x + w - 1, "│")
        win.attroff(border_attr)
        mid_y = y + h // 2
        mid_x = x + w // 2 - 1
        win.addstr(mid_y, mid_x, " + ", curses.color_pair(skins.C_PILL) | curses.A_BOLD)
    except curses.error:
        pass


# ── Expanded card renderer ────────────────────────────────────────────────────

def draw_expanded_card(win, card: CardDef, row_offset: int, sel_row: int) -> int:
    """Fill `win` with the expanded card view. Returns total data row count."""
    skin = skins.ACTIVE
    h, w = win.getmaxyx()

    win.erase()

    # Title bar
    title = f"  {card.label}  "
    try:
        win.addstr(0, 0, title, curses.color_pair(skins.C_HEADER) | curses.A_BOLD | curses.A_REVERSE)
        win.addstr(0, len(title), " " * (w - len(title)),
                   curses.color_pair(skins.C_HEADER) | curses.A_REVERSE)
    except curses.error:
        pass

    # Header row + data
    rows, cols = _run_expand_query(card)
    if cols:
        col_w = max(1, (w - 2) // len(cols))
        header_line = "  " + "".join(c[:col_w - 1].ljust(col_w) for c in cols)
        try:
            win.addstr(2, 0, header_line[:w], curses.color_pair(skins.C_DIM) | curses.A_UNDERLINE)
        except curses.error:
            pass

    # Data rows
    visible_h = h - 6  # title + blank + header + blank + actions + margin
    for i, row in enumerate(rows[row_offset: row_offset + visible_h]):
        vy = 3 + i
        is_sel = (i + row_offset == sel_row)
        attr = curses.color_pair(skins.C_SELECT) | curses.A_REVERSE if is_sel else curses.color_pair(skins.C_BLUE)
        line = "  "
        for col in (cols or []):
            val = str(row.get(col, ""))[:col_w - 1].ljust(col_w)
            line += val
        try:
            win.addstr(vy, 0, line[:w], attr)
        except curses.error:
            pass

    # Action hints at bottom
    if card.actions:
        hints = "  " + "  ".join(f"{a['key']}={a['label']}" for a in card.actions) + "  Esc=back"
    else:
        hints = "  Esc=back"
    try:
        win.addstr(h - 2, 0, hints[:w], curses.color_pair(skins.C_DIM))
    except curses.error:
        pass

    return len(rows)
