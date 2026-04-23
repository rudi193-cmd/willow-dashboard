#!/usr/bin/env python3
"""
Willow System Dashboard — terminal UI
dashboard.py  b17: WDASH  ΔΣ=42

Run: python3 dashboard.py
Set WILLOW_AGENT_NAME to choose which agent runs the session (default: heimdallr).
Keys: Tab=focus  ←→=page  ↑↓=navigate  Enter=expand  Esc=back  1-9=jump  r=refresh  q=quit
"""
import curses
import threading
import time
import os
import json
import re
import shutil
import sys
import urllib.request
import urllib.error
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soil
import skins
import cards as card_mod
import shutdown as shutdown_mod

# ── Color pairs ──────────────────────────────────────────────────────────────
C_DEFAULT  = 0
C_BLUE     = 1
C_GREEN    = 2
C_AMBER    = 3
C_DIM      = 4
C_HEADER   = 5
C_PILL     = 6
C_RED      = 7
C_BROWN    = 8
C_SELECT   = 9   # selected card / focused item

# Sender/agent hash palette — 7 stable colors (pairs 11-17)
C_HASH_1 = 11  # cyan
C_HASH_2 = 12  # magenta
C_HASH_3 = 13  # yellow
C_HASH_4 = 14  # green
C_HASH_5 = 15  # blue
C_HASH_6 = 16  # red
C_HASH_7 = 17  # cyan (bold variant)

# ── Pages ────────────────────────────────────────────────────────────────────
PAGE_OVERVIEW   = 0
PAGE_KART       = 1
PAGE_YGGDRASIL  = 2
PAGE_KNOWLEDGE  = 3
PAGE_SECRETS    = 4
PAGE_AGENTS     = 5
PAGE_LOGS       = 6
PAGE_SETTINGS   = 7
PAGE_HELP       = 8
PAGE_NAMES = ["Overview", "Kart", "Yggdrasil", "Knowledge", "Secrets", "Agents", "Logs", "Settings", "Help"]

REFRESH_INTERVAL = 30
SWAY_INTERVAL    = 2.0

# ── Willow animation ─────────────────────────────────────────────────────────
_POSE_L = [
    r"ƒƒ\ ƒ ƒ ƒ  /ƒ ƒ ",
    r"ƒ ƒ\ ƒ ƒ  / ƒ ƒ ",
    r"ƒ  ƒ\ ƒ  /  ƒ ƒ ",
    r"ƒ  ƒ \  / ƒ  ƒ  ",
    r"ƒ  ƒ  \/  ƒ  ƒ  ",
    r"ƒ  ƒ  ║   ƒ  ƒ  ",
    r"ƒ  ƒ ƒ║    ƒ  ƒ ",
    r"ƒ    ƒ║     ƒ  ƒ",
    r"ƒ     ║ƒ     ƒ  ",
    r"ƒ     ║ƒ      ƒ ",
]
_POSE_C = [
    r"ƒƒ\ ƒ ƒ ƒ /ƒ ƒ  ",
    r"ƒ ƒ\ ƒ ƒ / ƒ ƒ  ",
    r"ƒ  ƒ\   /  ƒ ƒ  ",
    r"ƒ  ƒ \ / ƒ  ƒ   ",
    r"ƒ  ƒ  ║  ƒ  ƒ   ",
    r"ƒ   ƒ ║  ƒ  ƒ   ",
    r"ƒ   ƒ ║ƒ  ƒ  ƒ  ",
    r"ƒ    ƒ║    ƒ  ƒ ",
    r"ƒ     ║ƒ    ƒ  ƒ",
    r"ƒ     ║ƒ     ƒ  ",
]
_POSE_R = [
    r"ƒ\ ƒ ƒ ƒ ƒ/ƒƒ   ",
    r"ƒ \ ƒ ƒ ƒ /ƒ ƒ  ",
    r"ƒ  \ ƒ ƒ /  ƒ ƒ ",
    r"ƒ ƒ \   /ƒ  ƒ ƒ ",
    r"ƒ ƒ  \ / ƒ  ƒ ƒ ",
    r"ƒ ƒ   ║  ƒ  ƒ ƒ ",
    r"ƒ  ƒ ƒ║   ƒ  ƒ  ",
    r"ƒ    ƒ║    ƒ  ƒ ",
    r"ƒ     ║ƒ    ƒ ƒ ",
    r"      ║ƒ     ƒ ƒ",
]
_SWAY_SEQ  = [_POSE_L, _POSE_C, _POSE_R, _POSE_C,
              _POSE_L, _POSE_C, _POSE_R, _POSE_C, _POSE_L, _POSE_C]
_POSE_DIRS = ['L',     'C',     'R',     'C',
              'L',     'C',     'R',     'C',     'L',     'C']

class _AnimState:
    def __init__(self):
        self.lock = threading.Lock()
        self.idx  = 0
        self.last = time.time()
    def tick(self):
        now = time.time()
        with self.lock:
            if now - self.last >= SWAY_INTERVAL:
                self.idx = (self.idx + 1) % len(_SWAY_SEQ)
                self.last = now
    def frame(self):
        with self.lock:
            return _SWAY_SEQ[self.idx]
    def direction(self):
        with self.lock:
            return _POSE_DIRS[self.idx]

ANIM = _AnimState()

# ── Scene elements ────────────────────────────────────────────────────────────
# Flowers: (row_from_bottom, col_from_tree_right, char)
# row_from_bottom: 0=grass line, 1=one above, 2=two above
_FLOWERS = [
    (0,  4,  '✿'),
    (0,  9,  '❀'),
    (0, 15,  '✾'),
    (0, 21,  '✿'),
    (0, 28,  '❁'),
    (0, 34,  '❀'),
    (0, 40,  '✿'),
    (1,  6,  '❀'),
    (1, 13,  '✿'),
    (1, 25,  '✾'),
    (1, 37,  '✿'),
    (2, 10,  '✾'),
    (2, 30,  '❁'),
]

_GRASS = "ˎ,ˏ',ˎ,ˏˎ,',ˎˏ,ˎ,',ˏ,ˎ',ˏˎ,',ˎ,ˏ'"

# ── Nav state ────────────────────────────────────────────────────────────────
class NavState:
    def __init__(self):
        self.page      = PAGE_OVERVIEW
        self.focus     = None        # None | "left" | "right"
        self.card_idx  = 0
        self.expanded  = False
        self.scroll      = 0         # left panel log scroll
        self.card_scroll = 0         # right panel grid scroll top row
        self.expand_row    = 0       # selected row inside expanded card
        self.confirm_action = None   # action dict pending y/n confirmation
        self.creating_card  = False  # True while Heimdallr interview is active
        self.search      = ""
        self.searching   = False
        self.quit_confirm = False   # waiting for second q to confirm exit
        self.nuke_mode  = False   # True when nuke placard is active
        self.nuke_input = ""      # characters typed toward "I UNDERSTAND"
    def tab(self):
        self.focus = {"right": None, "left": "right", None: "left"}[self.focus]
        self.expanded = False

NAV = NavState()

# ── Card catalog — loaded from SOIL at startup and on refresh ────────────────
_CARDS: list = []  # list[card_mod.CardDef]

def _load_cards() -> None:
    global _CARDS
    card_mod.seed_cards()
    _CARDS = card_mod.load_cards()
    _reload_catalog()


def _reload_catalog() -> None:
    global _catalog_states
    try:
        recs = {r["id"]: r for r in soil.all_records("willow-dashboard/cards")}
        _catalog_states = {c.id: bool(recs.get(c.id, {}).get("enabled", False))
                           for c in _CATALOG_SEEDS}
    except Exception:
        _catalog_states = {c.id: c.enabled for c in _CATALOG_SEEDS}

# ── Agent identity — read from env, resolved at runtime ──────────────────────
VERSION    = "0.2.0"
AGENT_NAME = os.environ.get("WILLOW_AGENT_NAME", "heimdallr")
APP_ID      = os.environ.get("WILLOW_APP_ID", AGENT_NAME)

# Known agent roles — supplemented at runtime from willow_agents registry
_AGENT_ROLES = {
    "heimdallr":  "Watchman. Gatekeeper. Stands at the Bifrost.",
    "gerald":     "Acting Dean. Philosophical. Holds the faculty together.",
    "oakenscroll":"Scroll-keeper. Long-form records. Custodian of history.",
    "shiva":      "Bridge Ring. SAFE face. Infrastructure destruction and renewal.",
    "nova":       "Exploration. New territory. First contact.",
    "jeles":      "Librarian. Special collections. Verification.",
    "riggs":      "Applied reality engineering. Gets things done.",
    "alexis":     "Analysis. Structured reasoning. Pattern recognition.",
    "ada":        "Systems admin. Continuity. Keeps things running.",
}

_WILLOW_CONTEXT = """\
Willow system architecture:
- SAP: portless auth gate, 49 tools, PGP-hardened, no HTTP
- SOIL: SQLite local store (78 collections, 2M+ records)
- LOAM: Postgres KB (68K atoms, 1M edges, unix socket peer auth)
- Kart: task queue worker, bubblewrap sandbox
- Yggdrasil: local SLM trained on Willow operational patterns
- SAFE: PGP-signed manifests for every professor app
- Faculty: Ada, Gerald, Jeles, Nova, Binder, Riggs, Hanz, Steve, Oakenscroll, Copenhagen, Ofshield, Alexis
Rules: Be terse. Name gaps explicitly. No padding. No apology. ΔΣ=42"""


def _load_agents():
    """Merge hardcoded roles with ~/.willow/agents.json local overrides."""
    agents = dict(_AGENT_ROLES)
    override = Path.home() / ".willow" / "agents.json"
    if override.exists():
        try:
            for entry in json.loads(override.read_text()):
                agents[entry["name"]] = entry.get("role", "Willow agent.")
        except Exception:
            pass
    return agents

ALL_AGENTS = _load_agents()


def _build_system_prompt(agent_name=None, card=None) -> str:
    name = agent_name or AGENT_NAME
    role = ALL_AGENTS.get(name, "Willow system agent.")
    base = f"You are {name.capitalize()}. {role}\n\n{_WILLOW_CONTEXT}"
    if card is None:
        return base
    # Inject live card context
    cached  = card_mod.cache_get(card.id)
    session = _load_session_atom(card.id)
    left_off = session.get("left_off_at", "")
    last_chat = session.get("last_chat", "")
    src = f"pg:{card.pg_table}" if card.pg_table else f"soil:{card.soil_collection}" if card.soil_collection else "runtime"
    ctx_lines = [
        f"\nActive project: {card.label}  [{card.id}]",
        f"  Value: {cached.get('value','—')}  {cached.get('sub','')}  ({cached.get('state','')})".rstrip(),
        f"  Data source: {src}",
    ]
    if card.actions:
        ctx_lines.append("  Actions: " + ", ".join(f"{a['key']}={a['label']}" for a in card.actions))
    if left_off:
        ctx_lines.append(f"  Last session: {left_off}")
    if last_chat:
        ctx_lines.append(f"  Last exchange: {last_chat}")
    return base + "\n" + "\n".join(ctx_lines)

AGENT_SYSTEM = _build_system_prompt()

# ── Chat state ────────────────────────────────────────────────────────────────
class ChatState:
    def __init__(self):
        self.lock          = threading.Lock()
        self.history       = []        # global [{role, content}]
        self.card_histories = {}       # {card_id: [{role, content}]}
        self.card_context  = None      # card_id currently bound, or None
        self.input         = ""
        self.typing        = False
        self.waiting       = False
        self.stream        = ""
        self.error         = None
        self.last_provider = "—"     # last model that responded
        self.card_creation_mode = False

    def add(self, role, content):
        with self.lock:
            self.history.append({"role": role, "content": content})
            if self.card_context:
                self.card_histories.setdefault(self.card_context, [])
                self.card_histories[self.card_context].append({"role": role, "content": content})

    def set_context(self, card_id: str | None):
        """Switch active card context, persisting outgoing history."""
        with self.lock:
            if self.card_context and self.card_context != card_id:
                _persist_card_history(self.card_context,
                                      self.card_histories.get(self.card_context, []))
            self.card_context = card_id
            if card_id and card_id not in self.card_histories:
                self.card_histories[card_id] = _load_card_history(card_id)

    def visible(self, n=30):
        with self.lock:
            if self.card_context:
                hist = self.card_histories.get(self.card_context, [])
                return list(hist[-n:])
            return list(self.history[-n:])

CHAT = ChatState()

# ── Session atoms + card chat persistence ────────────────────────────────────

def _persist_card_history(card_id: str, history: list) -> None:
    """Save the last 50 messages for a card to SOIL."""
    if not history:
        return
    try:
        soil.put("willow-dashboard/chat", card_id, {"messages": history[-50:]})
    except Exception:
        pass


def _load_card_history(card_id: str) -> list:
    """Load saved chat history for a card from SOIL."""
    try:
        rec = soil.get("willow-dashboard/chat", card_id)
        return rec.get("messages", []) if rec else []
    except Exception:
        return []


def _write_session_atom(card) -> None:
    """Write a brief 'left off here' atom when collapsing a card. Fire-and-forget."""
    try:
        cached  = card_mod.cache_get(card.id)
        last_msg = ""
        with CHAT.lock:
            hist = CHAT.card_histories.get(card.id, [])
            if hist:
                last_msg = hist[-1].get("content", "")[:120]
        atom = {
            "card_id":    card.id,
            "label":      card.label,
            "left_off_at": datetime.now().isoformat(timespec="seconds"),
            "value":      cached.get("value", "—"),
            "sub":        cached.get("sub", ""),
            "state":      cached.get("state", ""),
            "expand_row": NAV.expand_row,
            "last_chat":  last_msg,
        }
        soil.put("willow-dashboard/sessions", card.id, atom)
        DATA.push_log(f"session saved: {card.label}")
    except Exception as ex:
        DATA.push_log(f"session atom error: {ex}")


def _load_session_atom(card_id: str) -> dict:
    """Retrieve the last saved session atom for a card. SOIL first, KB fallback."""
    try:
        result = soil.get("willow-dashboard/sessions", card_id)
        if result:
            return result
    except Exception:
        pass
    # KB fallback — search knowledge/atoms SOIL collection
    try:
        hits = soil.search("knowledge/atoms", card_id)
        if hits:
            return {"summary": hits[0].get("summary", ""), "source": "kb"}
    except Exception:
        pass
    return {}


# ── Switch-context detection ─────────────────────────────────────────────────
_SWITCH_WORDS = ("switch to", "work on", "open", "go to", "jump to",
                 "let's do", "back to", "focus on")

def _detect_switch(msg: str) -> str | None:
    """Return a card_id if the message is a project-switch request, else None."""
    low = msg.lower().strip()
    for phrase in _SWITCH_WORDS:
        if low.startswith(phrase):
            target = low[len(phrase):].strip().rstrip(".,!")
            # fuzzy match against card labels and ids
            for card in _CARDS:
                if (target in card.label.lower() or
                        target in card.id.lower() or
                        card.label.lower() in target):
                    return card.id
    return None


def _get_vault_key(name):
    """Read a named credential — checks Fernet vault then credentials.json fallback."""
    # Fernet vault
    try:
        vault    = Path.home() / ".willow_creds.db"
        key_path = Path.home() / ".willow_master.key"
        if vault.exists() and key_path.exists():
            from cryptography.fernet import Fernet
            f    = Fernet(key_path.read_bytes().strip())
            conn = sqlite3.connect(str(vault))
            row  = conn.execute("SELECT value_enc FROM credentials WHERE name=?", (name,)).fetchone()
            conn.close()
            if row:
                return f.decrypt(row[0]).decode()
    except Exception:
        pass
    # Plain JSON fallback — try both the given name and uppercase variant
    for creds_path in (
        Path.home() / ".willow" / "secrets" / "credentials.json",
        Path("/home/sean-campbell/.willow/secrets/credentials.json"),
    ):
        try:
            if creds_path.exists():
                data = json.loads(creds_path.read_text())
                return data.get(name) or data.get(name.upper())
        except Exception:
            pass
    return None


def _stream_ollama(messages):
    """Yield token strings from Ollama streaming API."""
    with DATA.lock:
        model = f"yggdrasil:{DATA.ollama_ygg}"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            token = obj.get("message", {}).get("content", "")
            if token:
                yield token
            if obj.get("done"):
                break


def _call_fleet(messages, provider, api_key):
    """Non-streaming call to a fleet provider (OpenAI-compat)."""
    endpoints = {
        "groq":      ("https://api.groq.com/openai/v1/chat/completions",       "llama-3.3-70b-versatile"),
        "cerebras":  ("https://api.cerebras.ai/v1/chat/completions",            "llama3.1-8b"),
        "sambanova": ("https://api.sambanova.ai/v1/chat/completions",           "Meta-Llama-3.3-70B-Instruct"),
        "novita":    ("https://api.novita.ai/v3/openai/chat/completions",       "llama-3.3-70b-instruct"),
    }
    if provider not in endpoints:
        return None
    url, model = endpoints[provider]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 512,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


_CARD_CREATION_TRIGGERS = (
    "add card", "create card", "new card", "track my", "track a",
    "add a new card", "i'd like to add a new card",
)

_CARD_CREATION_SYSTEM = """\
You are Heimdallr, Willow dashboard card creation assistant. Interview the user briefly then emit a card-def block.

Steps:
1. Ask: new project or import existing SOIL collection / Postgres table?
2a. New: ask what to track, field names, status values. Suggest a slug id.
2b. Import: ask for the collection/table name. Report schema and record count if you can infer it.
3. Ask what to show large on the grid card (value) and optional subtitle.
4. Ask what actions to show when the card is expanded (one key per action, type=chat or confirm).
5. Confirm choices, then emit the card-def block.

When ready, emit EXACTLY this fenced block (no extra text after the closing fence):
```card-def
{
  "id": "slug",
  "label": "Display Name",
  "category": "work|dev|personal",
  "soil_collection": "...",
  "pg_table": "...",
  "value_query": "SELECT ...",
  "sub_query": "SELECT ...",
  "sub_format": "{} items",
  "state_query": "SELECT 'green'",
  "expand_query": "SELECT ... LIMIT 50",
  "expand_columns": ["col1", "col2"],
  "actions": [{"key": "a", "label": "add item", "type": "chat"}],
  "refresh_interval": 60
}
```

SOIL SQL rules: table is always "records", JSON payload in "data" column.
Example value_query: SELECT COUNT(*) FROM records WHERE json_extract(data,'$.status')='active' AND deleted=0
Omit fields that don't apply. Be terse. No padding."""


def _detect_card_creation(msg: str) -> bool:
    low = msg.lower()
    return any(t in low for t in _CARD_CREATION_TRIGGERS)


def _extract_card_def(text: str) -> dict | None:
    m = re.search(r'```card-def\s*\n(.*?)```', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except Exception:
        return None


def _write_card_def(d: dict) -> str:
    existing = card_mod.load_cards()
    max_order = max((c.order for c in existing), default=6)
    d.setdefault("built_in", False)
    d.setdefault("enabled", True)
    d.setdefault("order", max_order + 1)
    try:
        card = card_mod.CardDef.from_dict(d)
        card_mod.save_card(card)
        _load_cards()
        return f"Card '{card.label}' added. Press r to see it on the grid."
    except Exception as ex:
        return f"Card write failed: {ex}"


def _maybe_process_card_def(reply: str) -> None:
    d = _extract_card_def(reply)
    if d is None:
        return
    with CHAT.lock:
        CHAT.card_creation_mode = False
    msg = _write_card_def(d)
    CHAT.add("system", msg)
    DATA.push_log(f"card-def: {msg}")


def send_chat(user_msg, system_override: str = ""):
    """Send a message to Heimdallr. Runs in a background thread."""
    # Check for project switch before sending to LLM
    switch_id = _detect_switch(user_msg)
    if switch_id:
        target_card = next((c for c in _CARDS if c.id == switch_id), None)
        if target_card:
            CHAT.set_context(switch_id)
            session = _load_session_atom(switch_id)
            cached  = card_mod.cache_get(switch_id)
            note    = session.get("left_off_at", "")
            last    = session.get("last_chat", "")
            lines   = [f"Switching to {target_card.label}."]
            lines.append(f"  {cached.get('value','—')}  {cached.get('sub','')}".rstrip())
            if note:  lines.append(f"  Last session: {note}")
            if last:  lines.append(f"  Last: {last}")
            CHAT.add("system", "\n".join(lines))
            with CHAT.lock:
                CHAT.waiting = False
            return

    if _detect_card_creation(user_msg):
        with CHAT.lock:
            CHAT.card_creation_mode = True

    CHAT.add("user", user_msg)
    with CHAT.lock:
        CHAT.waiting = True
        CHAT.stream  = ""
        CHAT.error   = None

    # Build prompt with active card context if bound
    ctx_card = None
    with CHAT.lock:
        cid           = CHAT.card_context
        creation_mode = CHAT.card_creation_mode
    if cid:
        ctx_card = next((c for c in _CARDS if c.id == cid), None)
    if system_override:
        system_prompt = system_override
    elif creation_mode:
        system_prompt = _CARD_CREATION_SYSTEM
    else:
        system_prompt = _build_system_prompt(card=ctx_card)

    messages = [{"role": "system", "content": system_prompt}] + CHAT.visible()

    # 1. Try Ollama streaming
    try:
        if DATA.ollama_running:
            full = ""
            for token in _stream_ollama(messages):
                with CHAT.lock:
                    CHAT.stream += token
                full += token
            if shutdown_mod.SHUTDOWN.active:
                full = shutdown_mod.process_agent_message(full)
            CHAT.add("assistant", full)
            _maybe_process_card_def(full)
            with CHAT.lock:
                CHAT.waiting       = False
                CHAT.stream        = ""
                CHAT.last_provider = f"ygg:{DATA.ollama_ygg}"
            return
    except Exception as ex:
        DATA.push_log(f"ollama chat fail: {ex}")

    # 2. Fleet fallback — try providers in order
    for provider, key_name in (
        ("groq",      "GROQ_API_KEY"),
        ("cerebras",  "CEREBRAS_API_KEY"),
        ("sambanova", "SAMBANOVA_API_KEY"),
        ("novita",    "NOVITA_API_KEY"),
    ):
        api_key = _get_vault_key(key_name)
        if not api_key:
            continue
        try:
            reply = _call_fleet(messages, provider, api_key)
            if reply:
                CHAT.add("assistant", reply)
                _maybe_process_card_def(reply)
                with CHAT.lock:
                    CHAT.waiting       = False
                    CHAT.stream        = ""
                    CHAT.last_provider = provider
                DATA.push_log(f"chat via {provider}")
                return
        except Exception as ex:
            DATA.push_log(f"{provider} fail: {ex}")
            continue

    with CHAT.lock:
        CHAT.waiting = False
        CHAT.error   = "No backend available — check Ollama or vault keys"
    CHAT.add("assistant", "[no backend available]")


# ── System data ──────────────────────────────────────────────────────────────
class SystemData:
    def __init__(self):
        self.lock = threading.Lock()
        self.ts              = "—"
        self.pg_knowledge    = "—"
        self.pg_edges        = "—"
        self.pg_entities     = "—"
        self.kart_pending    = "—"
        self.kart_running    = "—"
        self.kart_done       = "—"
        self.kart_tasks      = []   # list of recent task dicts
        self.ollama_running  = False
        self.ollama_ygg      = "—"
        self.ollama_models   = []
        self.manifests_pass  = "—"
        self.manifests_total = "—"
        self.manifests_list  = []   # list of (app_id, signed)
        self.secret_names    = []   # credential names only
        self.log             = ["Willow dashboard starting..."]
        # sysinfo — populated by fetch_sysinfo()
        self.sys_cpu  = 0   # 0-100 %
        self.sys_mem  = 0   # 0-100 %
        self.sys_disk = 0   # 0-100 %
        self.sys_tmp  = 0   # degrees C
        self._prev_cpu_stat: tuple[int, int] | None = None  # (total, idle)
        # Grove / orchestration — populated by fetch_grove()
        self.grove_agents:       list[dict] = []
        self.grove_channels:     list[dict] = []
        self.routing_decisions:  list[dict] = []

    def push_log(self, msg):
        with self.lock:
            self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
            if len(self.log) > 200:
                self.log = self.log[-200:]

DATA = SystemData()

# ── Fetch helpers ─────────────────────────────────────────────────────────────
def _fmt(n):
    if isinstance(n, int):
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000:     return f"{n/1_000:.0f}K"
    return str(n)

def _fmt_age(secs: int) -> str:
    """Return a compact age string: '30s', '5m', '2h'."""
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"

def _pg_connect():
    """Connect to Postgres via Unix socket (peer auth) or WILLOW_DB_URL if set."""
    import psycopg2
    dsn = os.environ.get("WILLOW_DB_URL", "")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        dbname=os.environ.get("WILLOW_PG_DB", "willow"),
        user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
    )


def fetch_postgres():
    try:
        conn = _pg_connect()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.knowledge")
        k = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public.knowledge_edges")
        e = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public.entities")
        en = cur.fetchone()[0]
        try:
            cur.execute("SELECT status, COUNT(*) FROM kart_task_queue GROUP BY status")
            kart = dict(cur.fetchall())
            cur.execute("""SELECT task_id, status, task, created_at
                           FROM kart_task_queue
                           ORDER BY created_at DESC LIMIT 20""")
            tasks = [{"id": r[0], "status": r[1], "cmd": r[2][:40], "ts": str(r[3])[:16]}
                     for r in cur.fetchall()]
        except Exception:
            kart, tasks = {}, []
        conn.close()
        with DATA.lock:
            DATA.pg_knowledge = _fmt(k)
            DATA.pg_edges     = _fmt(e)
            DATA.pg_entities  = _fmt(en)
            DATA.kart_pending = str(kart.get("pending", kart.get("queued", 0)))
            DATA.kart_running = str(kart.get("running", 0))
            DATA.kart_done    = str(kart.get("complete", kart.get("completed", 0)))
            DATA.kart_tasks   = tasks
        DATA.push_log(f"pg: {_fmt(k)} atoms · {_fmt(e)} edges")
    except ImportError:
        DATA.push_log("psycopg2 not available")
    except Exception as ex:
        DATA.push_log(f"pg error: {ex}")


def fetch_grove():
    """Fetch Grove agents, channels, and routing decisions into DATA."""
    try:
        import grove_reader
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


def fetch_ollama():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        ygg = sorted([m for m in models if "yggdrasil" in m.lower()], reverse=True)
        latest = ygg[0].split(":")[-1] if ygg else "none"
        with DATA.lock:
            DATA.ollama_running = True
            DATA.ollama_ygg     = latest
            DATA.ollama_models  = models
        DATA.push_log(f"ollama: {len(models)} models · yggdrasil {latest}")
        card_mod.cache_put("yggdrasil", latest, f"{len(models)} models", "green")
        card_mod.cache_put_rows("yggdrasil",
            [{"model": m} for m in models], ["model"])
    except Exception:
        with DATA.lock:
            DATA.ollama_running = False
            DATA.ollama_ygg     = "down"
        DATA.push_log("ollama: unreachable")
        card_mod.cache_put("yggdrasil", "down", "ollama unreachable", "red")

def fetch_manifests():
    try:
        safe_root = os.environ.get("WILLOW_SAFE_ROOT",
                    str(Path.home() / "SAFE_backup" / "Applications"))
        items, passed, total = [], 0, 0
        if os.path.isdir(safe_root):
            for app in sorted(os.listdir(safe_root)):
                mf  = Path(safe_root) / app / "manifest.json"
                sig = Path(safe_root) / app / "manifest.sig"
                if mf.exists():
                    total += 1
                    signed = sig.exists()
                    if signed: passed += 1
                    items.append((app, signed))
        with DATA.lock:
            DATA.manifests_pass  = str(passed)
            DATA.manifests_total = str(total)
            DATA.manifests_list  = items
        DATA.push_log(f"manifests: {passed}/{total} signed")
    except Exception as ex:
        DATA.push_log(f"manifest error: {ex}")

def fetch_secrets():
    try:
        vault_path = Path.home() / ".willow_creds.db"
        if not vault_path.exists():
            card_mod.cache_put("secrets", "no vault", "", "amber")
            return
        conn = sqlite3.connect(str(vault_path))
        rows = conn.execute("SELECT name, env_key FROM credentials ORDER BY name").fetchall()
        conn.close()
        with DATA.lock:
            DATA.secret_names = [{"name": r[0], "env_key": r[1]} for r in rows]
        DATA.push_log(f"secrets: {len(rows)} credentials")
        card_mod.cache_put("secrets", str(len(rows)), "credentials", "green" if rows else "dim")
        card_mod.cache_put_rows("secrets",
            [{"name": r[0], "env_key": r[1]} for r in rows], ["name", "env_key"])
    except Exception as ex:
        DATA.push_log(f"secrets error: {ex}")
        card_mod.cache_put("secrets", "error", str(ex)[:30], "red")


_FLEET_PROVIDERS = [
    ("groq",      "GROQ_API_KEY"),
    ("cerebras",  "CEREBRAS_API_KEY"),
    ("sambanova", "SAMBANOVA_API_KEY"),
    ("novita",    "NOVITA_API_KEY"),
]

def fetch_fleet():
    present = []
    for name, key in _FLEET_PROVIDERS:
        val = _get_vault_key(key) or _get_vault_key(key.lower())
        if val:
            present.append(name)
    total = len(_FLEET_PROVIDERS)
    count = len(present)
    sub   = "  ".join(present) if present else "none configured"
    state = "green" if count == total else "amber" if count > 0 else "red"
    card_mod.cache_put("fleet", f"{count} / {total}", sub, state)
    rows  = [{"provider": name, "key": "present" if name in present else "missing"}
             for name, _ in _FLEET_PROVIDERS]
    card_mod.cache_put_rows("fleet", rows, ["provider", "key"])
    DATA.push_log(f"fleet: {count}/{total} keys found")


def fetch_mcp():
    search_dirs = [
        Path.home(),
        Path.home() / "github" / "willow-dashboard",
        Path.home() / "github" / "willow-1.7",
        Path(os.environ.get("WILLOW_PROJECT_ROOT", str(Path.home() / "github"))),
    ]
    servers: dict[str, str] = {}  # name -> command
    seen_paths = set()
    for d in search_dirs:
        mcp_file = d / ".mcp.json"
        if mcp_file in seen_paths or not mcp_file.exists():
            continue
        seen_paths.add(mcp_file)
        try:
            data = json.loads(mcp_file.read_text())
            for name, cfg in data.get("mcpServers", {}).items():
                servers[name] = cfg.get("command", "")
        except Exception:
            pass
    count = len(servers)
    names = "  ".join(list(servers)[:4])
    state = "green" if count > 0 else "dim"
    card_mod.cache_put("mcp", str(count), names, state)
    card_mod.cache_put_rows("mcp",
        [{"server": name, "command": cmd} for name, cmd in servers.items()],
        ["server", "command"])
    DATA.push_log(f"mcp: {count} servers")

# ── Card action dispatch ──────────────────────────────────────────────────────

def _get_expand_row(card) -> dict:
    """Return the currently selected row from the expanded view cache."""
    rows, _ = card_mod._run_expand_query(card)
    if rows and 0 <= NAV.expand_row < len(rows):
        return rows[NAV.expand_row]
    return {}


def _chat_with_context(card, action: dict, row: dict) -> None:
    """Build a context-aware message and send to Heimdallr."""
    row_str = "  ".join(f"{k}: {v}" for k, v in row.items()) if row else ""
    label   = action.get("label", action.get("key", "?"))
    if row_str:
        msg = f"[{card.label}] {label} — {row_str}"
    else:
        msg = f"[{card.label}] {label}"
    with CHAT.lock:
        CHAT.input = ""
    threading.Thread(target=send_chat, args=(msg,), daemon=True).start()
    NAV.expanded = False
    NAV.focus    = "left"


def _execute_confirm(card, action: dict, row: dict) -> None:
    """Execute a confirmed action. Runs in a background thread."""
    key  = action.get("key", "")
    name = card.id

    if name == "kart":
        task_id = row.get("task_id") or row.get("id", "")
        if not task_id:
            DATA.push_log("kart action: no task selected")
            return
        try:
            conn = card_mod._pg_conn()
            cur  = conn.cursor()
            if key == "c":
                cur.execute("UPDATE public.kart_task_queue SET status='cancelled' WHERE task_id=%s", (task_id,))
                DATA.push_log(f"kart: cancelled {task_id}")
            elif key == "r":
                cur.execute("UPDATE public.kart_task_queue SET status='pending' WHERE task_id=%s", (task_id,))
                DATA.push_log(f"kart: retried {task_id}")
            conn.commit()
            conn.close()
            threading.Thread(target=fetch_postgres, daemon=True).start()
        except Exception as ex:
            DATA.push_log(f"kart action error: {ex}")

    elif name == "secrets":
        cred_name = row.get("name", "")
        if not cred_name:
            return
        val = _get_vault_key(cred_name) or _get_vault_key(row.get("env_key", ""))
        if val:
            CHAT.add("system", f"[Secrets] {cred_name} = {val}")
        else:
            CHAT.add("system", f"[Secrets] {cred_name}: not found in vault")
        NAV.focus = "left"

    elif name == "fleet":
        provider = row.get("provider", "")
        if not provider:
            return
        endpoints = {
            "groq":      "https://api.groq.com/openai/v1/models",
            "cerebras":  "https://api.cerebras.ai/v1/models",
            "sambanova": "https://api.sambanova.ai/v1/models",
            "novita":    "https://api.novita.ai/v3/openai/models",
        }
        key_name = f"{provider.upper()}_API_KEY"
        api_key  = _get_vault_key(key_name) or _get_vault_key(key_name.lower())
        url = endpoints.get(provider, "")
        if not api_key or not url:
            DATA.push_log(f"fleet ping {provider}: no key")
            return
        try:
            req = urllib.request.Request(url,
                headers={"Authorization": f"Bearer {api_key}"})
            with urllib.request.urlopen(req, timeout=5) as r:
                status = r.status
            DATA.push_log(f"fleet ping {provider}: {status} OK")
            CHAT.add("system", f"[Fleet] {provider}: {status} OK")
        except urllib.error.HTTPError as e:
            DATA.push_log(f"fleet ping {provider}: {e.code}")
            CHAT.add("system", f"[Fleet] {provider}: HTTP {e.code}")
        except Exception as ex:
            DATA.push_log(f"fleet ping {provider}: {ex}")
        NAV.focus = "left"

    else:
        # Generic confirm — hand off to chat with context
        _chat_with_context(card, action, row)


def _dispatch_action(card, action: dict) -> None:
    """Route an action key press to chat or confirm flow."""
    row = _get_expand_row(card)
    if action.get("type") == "chat":
        _chat_with_context(card, action, row)
    elif action.get("type") == "confirm":
        NAV.confirm_action = action
    # form type: not yet implemented


def fetch_agents():
    count  = len(ALL_AGENTS)
    active = AGENT_NAME
    card_mod.cache_put("agents", str(count), f"active: {active}", "green")
    card_mod.cache_put_rows("agents",
        [{"name": name, "role": role[:60]} for name, role in ALL_AGENTS.items()],
        ["name", "role"])


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
    except Exception as ex:
        DATA.push_log(f"sysinfo cpu error: {ex}")

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
    except Exception as ex:
        DATA.push_log(f"sysinfo mem error: {ex}")

    # DISK — root filesystem usage
    try:
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


def refresh_all():
    with DATA.lock:
        DATA.ts = datetime.now().strftime("%H:%M:%S")
    DATA.push_log("── refreshing ──")
    fetch_sysinfo()
    fetch_postgres()
    fetch_grove()
    fetch_ollama()
    fetch_manifests()
    fetch_secrets()
    fetch_fleet()
    fetch_mcp()
    fetch_agents()
    card_mod.refresh_card_values(_CARDS)

def background_refresh(stop_evt):
    while not stop_evt.is_set():
        refresh_all()
        stop_evt.wait(REFRESH_INTERVAL)

# ── Drawing helpers ───────────────────────────────────────────────────────────
def safe_addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w: return
    max_len = w - x - 1
    if max_len <= 0: return
    try: win.addstr(y, x, text[:max_len], attr)
    except curses.error: pass

def draw_hline(win, y, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h: return
    try: win.hline(y, 0, curses.ACS_HLINE, w - 1, attr)
    except curses.error: pass

def _ascii_bar(pct: int, width: int = 8) -> str:
    """Return a filled/empty block bar string representing pct (0-100)."""
    pct = max(0, min(100, pct))
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

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

    tmp_col = C_AMBER if tmp > 70 else C_DIM
    tmp_str = f" TMP {tmp}°C"
    if x + len(tmp_str) < w - 1:
        safe_addstr(win, y, x, tmp_str, curses.color_pair(tmp_col))

def draw_panel_border(win, focused):
    attr = (curses.color_pair(C_AMBER) | curses.A_BOLD) if focused else \
           (curses.color_pair(C_DIM) | curses.A_DIM)
    try: win.border(
        curses.ACS_VLINE, curses.ACS_VLINE,
        curses.ACS_HLINE, curses.ACS_HLINE,
        curses.ACS_ULCORNER, curses.ACS_URCORNER,
        curses.ACS_LLCORNER, curses.ACS_LRCORNER,
    )
    except curses.error: pass
    # re-colour the border by drawing over with attr
    h, w = win.getmaxyx()
    try:
        win.attron(attr)
        win.hline(0,   0, curses.ACS_HLINE, w - 1)
        win.hline(h-1, 0, curses.ACS_HLINE, w - 1)
        for y in range(1, h - 1):
            win.addch(y, 0,     curses.ACS_VLINE)
            win.addch(y, w - 2, curses.ACS_VLINE)
        win.addch(0,   0,     curses.ACS_ULCORNER)
        win.addch(0,   w - 2, curses.ACS_URCORNER)
        win.addch(h-1, 0,     curses.ACS_LLCORNER)
        win.addch(h-1, w - 2, curses.ACS_LRCORNER)
        win.attroff(attr)
    except curses.error: pass

# ── Willow hero (shared left-panel top) ──────────────────────────────────────
_TREE_H = len(_POSE_C)
_TREE_W = max(len(l) for l in _POSE_C)

def draw_willow_hero(win):
    h, w = win.getmaxyx()
    ANIM.tick()
    frame   = ANIM.frame()
    wind    = ANIM.direction()
    w_off   = {'L': -2, 'C': 0, 'R': 2}[wind]   # flower drift

    # Title row
    safe_addstr(win, 0, 2, "W I L L O W", curses.color_pair(C_BLUE) | curses.A_BOLD)
    safe_addstr(win, 0, 14, "● LIVE", curses.color_pair(C_GREEN))
    safe_addstr(win, 0, 22, f"[ {AGENT_NAME} ]", curses.color_pair(C_AMBER))
    # Sun top-right
    sun_x = w - 4
    if sun_x > 30:
        safe_addstr(win, 0, sun_x, "☀", curses.color_pair(C_AMBER) | curses.A_BOLD)

    # Tree — anchored left
    tree_x = 2
    for i, line in enumerate(frame):
        y = 1 + i
        if y >= h: break
        for j, ch in enumerate(line):
            x = tree_x + j
            if x >= w - 1: break
            if ch == '║':
                attr = curses.color_pair(C_BROWN) | curses.A_BOLD
            elif ch in ('/', '\\', 'V'):
                attr = curses.color_pair(C_GREEN)
            elif ch == 'ƒ':
                attr = curses.color_pair(C_GREEN) | curses.A_DIM
            else:
                continue
            try: win.addch(y, x, ch, attr)
            except curses.error: pass

    # Flowers — growing from the ground, drift with wind
    flower_x0 = tree_x + _TREE_W + 3
    grass_row  = _TREE_H + 1
    for (row_from_bot, col, fch) in _FLOWERS:
        y = grass_row - row_from_bot
        x = flower_x0 + col + w_off
        if 1 <= y < h and flower_x0 <= x < w - 2:
            try: win.addch(y, x, fch, curses.color_pair(C_GREEN))
            except curses.error: pass

    # Grass line — shifts 1 char with wind
    grass_row = _TREE_H + 1
    if grass_row < h:
        g_off = {'L': 1, 'C': 0, 'R': -1}[wind]
        for x in range(w - 1):
            gch = _GRASS[(x + g_off) % len(_GRASS)]
            try: win.addch(grass_row, x, gch, curses.color_pair(C_GREEN) | curses.A_DIM)
            except curses.error: pass

    # Agent name — sits on grass line, right-justified
    agent = f"{AGENT_NAME.capitalize()} · Sonnet 4.6"
    safe_addstr(win, _TREE_H, w - len(agent) - 2, agent, curses.color_pair(C_DIM))

    _draw_hero_vitals(win, _TREE_H + 2)
    return _TREE_H + 3

def draw_stat_strip(win):
    h, w = win.getmaxyx()
    draw_hline(win, h - 2, curses.color_pair(C_DIM))
    with DATA.lock:
        kb = DATA.pg_knowledge; edges = DATA.pg_edges; ygg = DATA.ollama_ygg; ts = DATA.ts
    pills = [f" 49 Tools ", f" {kb} KB ", f" {edges} Edges ", f" ygg:{ygg} ", f" {ts} "]
    x = 1
    for pill in pills:
        safe_addstr(win, h - 1, x, pill, curses.color_pair(C_PILL))
        x += len(pill) + 1
        if x >= w - 2: break

# ── Title bar (row 0) ────────────────────────────────────────────────────────
def draw_title_bar(stdscr):
    h, w = stdscr.getmaxyx()
    with CHAT.lock:
        provider = CHAT.last_provider
    with DATA.lock:
        ts = DATA.ts

    # Left: product name
    title = f" WILLOW DASHBOARD  v{VERSION} "
    agent = f" {AGENT_NAME.upper()} "

    # Right: time · agent · provider
    right = f" {ts}  ·  {agent.strip()}  ·  {provider} "

    try:
        stdscr.addstr(0, 0, title,
                      curses.color_pair(C_HEADER) | curses.A_BOLD | curses.A_REVERSE)
        stdscr.addstr(0, len(title), agent,
                      curses.color_pair(C_PILL) | curses.A_REVERSE)
        fill_start = len(title) + len(agent)
        fill_end   = max(fill_start, w - len(right) - 1)
        stdscr.addstr(0, fill_start, " " * (fill_end - fill_start),
                      curses.color_pair(C_DIM) | curses.A_REVERSE)
        if fill_end + len(right) < w:
            stdscr.addstr(0, fill_end, right,
                          curses.color_pair(C_DIM) | curses.A_REVERSE)
    except curses.error:
        pass


# ── Page tab bar (last row) ───────────────────────────────────────────────────
def draw_page_bar(stdscr):
    h, w = stdscr.getmaxyx()
    y = h - 1
    x = 0
    for i, name in enumerate(PAGE_NAMES):
        active = (i == NAV.page)
        label  = f" {i+1}·{name} " if active else f" {name} "
        if active:
            tab_col = C_AMBER if NAV.focus is not None else C_BLUE
            attr = curses.color_pair(tab_col) | curses.A_BOLD | curses.A_REVERSE
        else:
            attr = curses.color_pair(C_DIM) | curses.A_DIM
        if x + len(label) < w:
            try: stdscr.addstr(y, x, label, attr)
            except curses.error: pass
            x += len(label) + 1
    if NAV.quit_confirm:
        hint = "  Press Q again to quit — any other key to cancel  "
        hx = w - len(hint) - 1
        if hx > x:
            try: stdscr.addstr(y, hx, hint,
                               curses.color_pair(C_AMBER) | curses.A_BOLD | curses.A_REVERSE)
            except curses.error: pass
    else:
        hint = " Tab=focus ←→=page Enter=expand Esc=back n=nuke qq=quit "
        hx = w - len(hint) - 1
        if hx > x:
            try: stdscr.addstr(y, hx, hint, curses.color_pair(C_DIM))
            except curses.error: pass

# ── Overview page ─────────────────────────────────────────────────────────────
def draw_overview_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    focused   = NAV.focus == "left"

    _section_header(win, content_y, "COMMAND")
    content_y += 1

    # ── Chat history ──
    input_row  = h - 3   # ▸ prompt row (above stat strip)
    sep_row    = h - 4   # thin line between chat and input
    chat_top   = content_y
    chat_bot   = sep_row
    chat_h     = chat_bot - chat_top

    history = CHAT.visible(50)
    # expand multi-line messages into display lines
    display_lines = []
    for msg in history:
        prefix = "you: " if msg["role"] == "user" else "heim: "
        col    = C_DIM if msg["role"] == "user" else C_BLUE
        text   = msg["content"].replace("\n", " ")
        max_w  = w - len(prefix) - 4
        # word-wrap
        words, line = text.split(), ""
        for word in words:
            if len(line) + len(word) + 1 > max_w:
                display_lines.append((prefix if not line else "      ", line.strip(), col))
                line = word
                prefix = "      "
            else:
                line = (line + " " + word).strip()
        if line:
            display_lines.append((prefix, line, col))

    # streaming buffer
    with CHAT.lock:
        stream = CHAT.stream
        waiting = CHAT.waiting
    if stream:
        display_lines.append(("heim: ", stream + "▌", C_BLUE))
    elif waiting:
        display_lines.append(("heim: ", "▌", C_BLUE))

    # show most recent lines
    visible = display_lines[-(chat_h):]
    for i, (prefix, text, col) in enumerate(visible):
        y = chat_top + i
        if y >= chat_bot: break
        safe_addstr(win, y, 2, prefix, curses.color_pair(C_DIM) | curses.A_DIM)
        safe_addstr(win, y, 2 + len(prefix), text[:w - len(prefix) - 4], curses.color_pair(col))

    # ── Separator above input ──
    draw_hline(win, sep_row, curses.color_pair(C_DIM))

    # ── Input row ──
    with CHAT.lock:
        inp = CHAT.input
        typing = CHAT.typing
    if typing or focused:
        safe_addstr(win, input_row, 1, "▸", curses.color_pair(C_AMBER) | curses.A_BOLD)
        display_input = inp[-w+5:] if len(inp) > w - 5 else inp
        safe_addstr(win, input_row, 3, display_input, curses.color_pair(C_DIM))
        if focused:
            cx = min(3 + len(display_input), w - 2)
            try: win.move(input_row, cx)
            except curses.error: pass
    else:
        safe_addstr(win, input_row, 1, "▸", curses.color_pair(C_DIM))
        safe_addstr(win, input_row, 3, f"ask {AGENT_NAME}...", curses.color_pair(C_DIM) | curses.A_DIM)

    draw_stat_strip(win)
    draw_panel_border(win, focused)
    win.noutrefresh()

def draw_shutdown_right(win):
    """Right panel view during graceful shutdown."""
    h, w = win.getmaxyx()
    win.erase()
    sd = shutdown_mod.SHUTDOWN

    safe_addstr(win, 0, 1, "SHUTTING DOWN", curses.color_pair(C_AMBER) | curses.A_BOLD)
    if sd.raw_mode:
        safe_addstr(win, 0, w - 12, " RAW MODE ", curses.color_pair(C_DIM))

    y = 2
    for n, desc, _ in shutdown_mod.STEPS:
        if y >= h - 2:
            break
        status = sd.status_for(n)
        icon   = shutdown_mod.STEP_ICONS.get(status, "○")

        if status == "done":
            attr = curses.color_pair(C_GREEN)
        elif status == "running":
            attr = curses.color_pair(C_AMBER) | curses.A_BOLD
        elif status == "error":
            attr = curses.color_pair(C_RED)
        else:
            attr = curses.color_pair(C_DIM)

        safe_addstr(win, y, 2, f" {icon}  {desc}", attr)

        # Show current step detail line
        if status == "running" and not sd.raw_mode:
            safe_addstr(win, y + 1, 6,
                        "Working...", curses.color_pair(C_DIM) | curses.A_DIM)
            y += 2
        else:
            y += 1

    if sd.complete:
        safe_addstr(win, h - 3, 2,
                    "  Session closed. Press Q to exit.",
                    curses.color_pair(C_GREEN) | curses.A_BOLD)
    elif not sd.raw_mode:
        safe_addstr(win, h - 2, 2,
                    "  Q = force quit without finishing",
                    curses.color_pair(C_DIM))

    draw_panel_border(win, False)
    win.noutrefresh()


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
            glyph, glyph_col = "•", C_AMBER
            suffix = f" {unread}"
        else:
            glyph, glyph_col = "·", C_DIM
            suffix = ""
        safe_addstr(win, y, 2, f"#{name}", curses.color_pair(C_BLUE))
        x_g = 2 + 1 + len(name) + 2
        if x_g < w - 4:
            safe_addstr(win, y, x_g, glyph + suffix, curses.color_pair(glyph_col))
        y += 1
    return y


def draw_overview_right(win):
    if shutdown_mod.SHUTDOWN.active:
        draw_shutdown_right(win)
        return
    h, w = win.getmaxyx()
    win.erase()
    focused = NAV.focus == "right"

    with DATA.lock:
        pg_kb     = DATA.pg_knowledge
        pg_edges  = DATA.pg_edges
        kp        = DATA.kart_pending
        kr        = DATA.kart_running
        kd        = DATA.kart_done
        ollama_up = DATA.ollama_running
        ygg       = DATA.ollama_ygg
        safe_p    = DATA.manifests_pass
        safe_t    = DATA.manifests_total
        cpu       = DATA.sys_cpu
        mem       = DATA.sys_mem
        tmp       = DATA.sys_tmp

    # Expanded card view takes over the whole panel
    if NAV.expanded and focused and 0 <= NAV.card_idx < len(_CARDS):
        card = _CARDS[NAV.card_idx]
        row_count = card_mod.draw_expanded_card(
            win, card, NAV.expand_row, NAV.expand_row,
            confirm_action=NAV.confirm_action,
            session_atom=_load_session_atom(card.id))
        NAV._expand_total = row_count
        draw_panel_border(win, focused)
        win.noutrefresh()
        return

    # ── Compact STATUS strip (one line per system) ────────────────────────────
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

    rows = [
        ("●", "Postgres", f"{pg_kb} {pg_edges}e", C_GREEN),
        ("▲" if kp_warn else "●", "Kart",
         f"{kp}q {kr}r", C_AMBER if kp_warn else C_GREEN),
        ("●" if ollama_up else "✗", "Ollama",
         f"{ygg}", C_GREEN if ollama_up else C_RED),
        ("●" if safe_ok else "▲", "SAFE",
         f"{safe_p}/{safe_t}", C_GREEN if safe_ok else C_AMBER),
    ]
    for dot, name, metric, col in rows:
        name_w = max(1, w - len(dot) - len(metric) - 4)
        line = f"{dot} {name:<{name_w}}{metric}"
        safe_addstr(win, y, 1, line[:w - 2], curses.color_pair(col)); y += 1

    # Single vitals line: CPU bar + % + TMP
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
        gr_agents   = list(DATA.grove_agents)
        gr_channels = list(DATA.grove_channels)
        gr_routing  = list(DATA.routing_decisions)

    remaining = h - y - 4  # reserve 4 rows for card section
    if remaining >= 3:
        y = _draw_agents_region(win, y, w, gr_agents)
    if remaining >= 6:
        y = _draw_routing_region(win, y, w, gr_routing)
    if remaining >= 3:
        y = _draw_grove_region(win, y, w, gr_channels)

    # ── Card grid fills remaining space ───────────────────────────────────────
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

    draw_panel_border(win, focused)
    win.noutrefresh()

# ── Kart page ─────────────────────────────────────────────────────────────────
def draw_kart_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    safe_addstr(win, content_y, 2, "Kart Task Queue", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        kp = DATA.kart_pending; kr = DATA.kart_running; kd = DATA.kart_done
    safe_addstr(win, content_y + 1, 2,
        f"pending:{kp}  running:{kr}  done:{kd}",
        curses.color_pair(C_DIM))
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_kart_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "Recent Tasks", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        tasks = DATA.kart_tasks[:]
    focused = NAV.focus == "right"
    if not tasks:
        safe_addstr(win, 2, 2, "No tasks loaded — pg not connected", curses.color_pair(C_DIM))
    else:
        for i, t in enumerate(tasks[:h-3]):
            y = 1 + i
            selected = focused and i == NAV.card_idx
            status_col = C_GREEN if t["status"] in ("complete","completed") else \
                         C_AMBER if t["status"] == "running" else C_DIM
            attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else curses.color_pair(C_DIM)
            s_attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else curses.color_pair(status_col)
            label = f" {t['status'][:8]:<8} {t['cmd'][:w-14]} "
            safe_addstr(win, y, 1, label, attr)
    if NAV.expanded and tasks:
        t = tasks[min(NAV.card_idx, len(tasks)-1)]
        _draw_expanded_kart(win, t)
    win.noutrefresh()

def _draw_expanded_kart(win, t):
    h, w = win.getmaxyx()
    ew = min(w - 4, 60); eh = 8
    ey = max(1, (h - eh) // 2); ex = max(1, (w - ew) // 2)
    try:
        pop = win.derwin(eh, ew, ey, ex)
        pop.erase()
        pop.border()
        safe_addstr(pop, 0, 2, " Task Detail ", curses.color_pair(C_BLUE) | curses.A_BOLD)
        safe_addstr(pop, 1, 2, f"ID:     {t['id']}", curses.color_pair(C_DIM))
        safe_addstr(pop, 2, 2, f"Status: {t['status']}", curses.color_pair(C_GREEN))
        safe_addstr(pop, 3, 2, f"Cmd:    {t['cmd']}", curses.color_pair(C_DIM))
        safe_addstr(pop, 4, 2, f"Time:   {t['ts']}", curses.color_pair(C_DIM))
        safe_addstr(pop, eh-1, 2, " Esc=close ", curses.color_pair(C_DIM))
        pop.noutrefresh()
    except curses.error: pass

# ── Yggdrasil page ────────────────────────────────────────────────────────────
def draw_yggdrasil_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    safe_addstr(win, content_y, 2, "Yggdrasil — Local SLM", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        ygg = DATA.ollama_ygg; running = DATA.ollama_running
    status = "● LIVE" if running else "○ DOWN"
    scol = C_GREEN if running else C_RED
    safe_addstr(win, content_y + 1, 2, f"Active: yggdrasil:{ygg}  ", curses.color_pair(C_DIM))
    safe_addstr(win, content_y + 2, 2, status, curses.color_pair(scol))
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_yggdrasil_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "Models", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        models = DATA.ollama_models[:]
    focused = NAV.focus == "right"
    ygg_models = [m for m in models if "yggdrasil" in m.lower()]
    other = [m for m in models if "yggdrasil" not in m.lower()]
    items = ygg_models + ["──────────"] + other
    for i, name in enumerate(items[:h-3]):
        y = 1 + i
        if name.startswith("──"):
            safe_addstr(win, y, 2, name[:w-3], curses.color_pair(C_DIM) | curses.A_DIM)
            continue
        selected = focused and i == NAV.card_idx
        attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else \
               curses.color_pair(C_GREEN) if "yggdrasil" in name else curses.color_pair(C_DIM)
        safe_addstr(win, y, 2, f" {name[:w-4]} ", attr)
    draw_panel_border(win, NAV.focus == "right")
    win.noutrefresh()

# ── Knowledge page ────────────────────────────────────────────────────────────
def draw_knowledge_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    with DATA.lock:
        kb = DATA.pg_knowledge; edges = DATA.pg_edges
    safe_addstr(win, content_y,     2, "Knowledge Graph", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, content_y + 1, 2, f"{kb} atoms", curses.color_pair(C_BLUE) | curses.A_BOLD)
    safe_addstr(win, content_y + 2, 2, f"{edges} edges", curses.color_pair(C_DIM))
    safe_addstr(win, content_y + 4, 2, "Press / to search", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_knowledge_right(win):
    h, w = win.getmaxyx()
    win.erase()
    query = NAV.search
    if NAV.searching:
        safe_addstr(win, 0, 1, f"Search: {query}_", curses.color_pair(C_BLUE) | curses.A_BOLD)
    else:
        safe_addstr(win, 0, 1, f"Search: {query or '(press / to search)'}", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, 2, 2, "KB search not yet wired to MCP.", curses.color_pair(C_DIM))
    safe_addstr(win, 3, 2, "Will call willow_knowledge_search on enter.", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_panel_border(win, NAV.focus == "right")
    win.noutrefresh()

# ── Secrets page ──────────────────────────────────────────────────────────────
def draw_secrets_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    with DATA.lock:
        n = len(DATA.secret_names)
    safe_addstr(win, content_y,     2, "Credential Vault", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, content_y + 1, 2, f"{n} credentials stored", curses.color_pair(C_DIM))
    safe_addstr(win, content_y + 2, 2, "Fernet-encrypted SQLite", curses.color_pair(C_DIM) | curses.A_DIM)
    safe_addstr(win, content_y + 4, 2, "↑↓=navigate  Enter=reveal", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_secrets_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "Credentials  (names only)", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        secrets = DATA.secret_names[:]
    focused = NAV.focus == "right"
    if not secrets:
        safe_addstr(win, 2, 2, "Vault empty or not found.", curses.color_pair(C_DIM))
    for i, s in enumerate(secrets[:h-3]):
        y = 1 + i
        selected = focused and i == NAV.card_idx
        attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else curses.color_pair(C_DIM)
        env = f" → {s['env_key']}" if s['env_key'] else ""
        safe_addstr(win, y, 2, f" {s['name']}{env} "[:w-3], attr)
    if NAV.expanded and secrets:
        s = secrets[min(NAV.card_idx, len(secrets)-1)]
        _draw_secret_confirm(win, s)
    draw_panel_border(win, NAV.focus == "right")
    win.noutrefresh()

def _draw_secret_confirm(win, s):
    h, w = win.getmaxyx()
    ew = min(w - 4, 50); eh = 6
    ey = max(1, (h - eh) // 2); ex = max(1, (w - ew) // 2)
    try:
        pop = win.derwin(eh, ew, ey, ex)
        pop.erase(); pop.border()
        safe_addstr(pop, 0, 2, " Credential ", curses.color_pair(C_AMBER) | curses.A_BOLD)
        safe_addstr(pop, 1, 2, f"Name:    {s['name']}", curses.color_pair(C_DIM))
        safe_addstr(pop, 2, 2, f"Env key: {s['env_key'] or '—'}", curses.color_pair(C_DIM))
        safe_addstr(pop, 3, 2, "Value:   [protected]", curses.color_pair(C_AMBER))
        safe_addstr(pop, eh-1, 2, " Esc=close ", curses.color_pair(C_DIM))
        pop.noutrefresh()
    except curses.error: pass

# ── Agents page ───────────────────────────────────────────────────────────────
def draw_agents_left(win):
    h, w = win.getmaxyx()
    win.erase()
    content_y = draw_willow_hero(win)
    with DATA.lock:
        mfp = DATA.manifests_pass; mft = DATA.manifests_total
    safe_addstr(win, content_y,     2, "Agents & SAFE", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, content_y + 1, 2, f"Manifests: {mfp}/{mft} signed", curses.color_pair(C_DIM))
    safe_addstr(win, content_y + 2, 2, "PGP v2 · portless", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_agents_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "SAFE Manifests", curses.color_pair(C_HEADER) | curses.A_BOLD)
    with DATA.lock:
        items = DATA.manifests_list[:]
    focused = NAV.focus == "right"
    for i, (app_id, signed) in enumerate(items[:h-3]):
        y = 1 + i
        selected = focused and i == NAV.card_idx
        sig_str = "✓" if signed else "✗"
        sig_col = C_GREEN if signed else C_RED
        base_attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else curses.color_pair(C_DIM)
        safe_addstr(win, y, 2, f" {sig_str} {app_id[:w-7]} ", base_attr)
    draw_panel_border(win, NAV.focus == "right")
    win.noutrefresh()

# ── Logs page ─────────────────────────────────────────────────────────────────
def draw_logs_full(left_win, right_win):
    h, w_l = left_win.getmaxyx()
    _, w_r  = right_win.getmaxyx()
    left_win.erase(); right_win.erase()
    safe_addstr(left_win, 0, 1, "Activity Log", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(left_win, 0, w_l - 20, "↑↓=scroll  Esc=back", curses.color_pair(C_DIM))
    with DATA.lock:
        log = DATA.log[:]
    total = len(log)
    visible = h - 2
    offset = max(0, min(NAV.scroll, total - visible))
    lines = log[offset:offset + visible]
    for i, line in enumerate(lines):
        y = 1 + i
        if line.startswith("──"):
            attr = curses.color_pair(C_DIM) | curses.A_DIM
        elif "error" in line.lower():
            attr = curses.color_pair(C_RED)
        else:
            attr = curses.color_pair(C_DIM)
        safe_addstr(left_win, y, 1, line[:w_l-2], attr)
    scrollbar = f" {offset+1}-{min(offset+visible, total)}/{total} "
    safe_addstr(left_win, h-1, w_l - len(scrollbar) - 1, scrollbar, curses.color_pair(C_PILL))
    left_win.noutrefresh()
    right_win.noutrefresh()

# ── Settings page ────────────────────────────────────────────────────────────
_SETTINGS = [
    ("refresh_interval",  str(REFRESH_INTERVAL), "seconds between data refreshes"),
    ("sway_interval",     str(SWAY_INTERVAL),    "seconds per animation frame"),
    ("willow_db_url",     "env:WILLOW_DB_URL",   "Postgres DSN (optional — Unix socket used by default)"),
    ("safe_root",         "env:WILLOW_SAFE_ROOT", "SAFE manifests root path"),
    ("ollama_host",       "localhost:11434",      "Ollama API endpoint"),
]

def draw_settings_left(win):
    win.erase()
    content_y = draw_willow_hero(win)
    safe_addstr(win, content_y,     2, "Settings", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, content_y + 1, 2, "↑↓=navigate  Enter=edit", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

_SKIN_IDX_OFFSET    = len(_SETTINGS)
_CATALOG_SEEDS      = [c for c in card_mod.CARD_SEEDS if not c.built_in]
_CATALOG_IDX_OFFSET = _SKIN_IDX_OFFSET + len(skins.SKIN_SEEDS) + 1  # +1 for dev toggle
_catalog_states: dict[str, bool] = {c.id: c.enabled for c in _CATALOG_SEEDS}

def draw_settings_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "Configuration", curses.color_pair(C_HEADER) | curses.A_BOLD)
    focused = NAV.focus == "right"

    # Config settings
    for i, (key, val, desc) in enumerate(_SETTINGS):
        y = 2 + i * 3
        if y + 2 >= h: break
        selected = focused and i == NAV.card_idx
        k_attr = curses.color_pair(C_SELECT) | curses.A_REVERSE if selected else curses.color_pair(C_AMBER)
        safe_addstr(win, y,     2, f" {key} ", k_attr)
        safe_addstr(win, y + 1, 4, val[:w-6],  curses.color_pair(C_BLUE))
        safe_addstr(win, y + 2, 4, desc[:w-6], curses.color_pair(C_DIM) | curses.A_DIM)

    # Skin picker
    skin_y = 2 + len(_SETTINGS) * 3 + 1
    if skin_y < h - 2:
        safe_addstr(win, skin_y, 1, "── Skin ──", curses.color_pair(C_AMBER))
        for i, skin in enumerate(skins.SKIN_SEEDS):
            y = skin_y + 1 + i
            if y >= h - 1: break
            active   = skin.id == skins.ACTIVE.id
            sel_idx  = _SKIN_IDX_OFFSET + i
            selected = focused and NAV.card_idx == sel_idx
            if selected:
                attr = curses.color_pair(C_SELECT) | curses.A_REVERSE
            elif active:
                attr = curses.color_pair(C_GREEN) | curses.A_BOLD
            else:
                attr = curses.color_pair(C_DIM)
            marker = "▶ " if active else "  "
            hint   = "  ← active" if active else ""
            safe_addstr(win, y, 2, f"{marker}{skin.label}{hint}"[:w-4], attr)

    # Card catalog — enable / disable optional cards
    cat_y = skin_y + len(skins.SKIN_SEEDS) + 2
    if cat_y < h - 2:
        safe_addstr(win, cat_y, 1, "── Card Catalog ──", curses.color_pair(C_AMBER))
        for i, seed in enumerate(_CATALOG_SEEDS):
            y = cat_y + 1 + i
            if y >= h - 1: break
            sel_idx  = _CATALOG_IDX_OFFSET + i
            selected = focused and NAV.card_idx == sel_idx
            enabled  = _catalog_states.get(seed.id, False)
            if selected:
                attr = curses.color_pair(C_SELECT) | curses.A_REVERSE
            elif enabled:
                attr = curses.color_pair(C_GREEN) | curses.A_BOLD
            else:
                attr = curses.color_pair(C_DIM)
            check = "[x]" if enabled else "[ ]"
            safe_addstr(win, y, 2,
                        f"{check} {seed.label:<20} {seed.category}"[:w-4], attr)

    # Developer options
    dev_y = cat_y + len(_CATALOG_SEEDS) + 2
    if dev_y < h - 4:
        safe_addstr(win, dev_y, 1, "── Developer ──", curses.color_pair(C_AMBER))
        raw_on  = shutdown_mod.SHUTDOWN.raw_mode
        sel_dev = focused and NAV.card_idx == _SKIN_IDX_OFFSET + len(skins.SKIN_SEEDS)
        dev_attr = (curses.color_pair(C_SELECT) | curses.A_REVERSE if sel_dev
                    else curses.color_pair(C_GREEN) | curses.A_BOLD if raw_on
                    else curses.color_pair(C_DIM))
        marker = "▶ " if raw_on else "  "
        safe_addstr(win, dev_y + 1, 2,
                    f"{marker}Shutdown raw mode  {'(on)' if raw_on else '(off)'}",
                    dev_attr)
        safe_addstr(win, dev_y + 2, 6,
                    "Show agent output unfiltered during shutdown",
                    curses.color_pair(C_DIM) | curses.A_DIM)

    # Agent list
    agent_y = dev_y + 5
    if agent_y < h - 2:
        safe_addstr(win, agent_y, 1, "── Registered Agents ──", curses.color_pair(C_AMBER))
        for i, (name, role) in enumerate(ALL_AGENTS.items()):
            y = agent_y + 1 + i
            if y >= h - 1: break
            active = name == AGENT_NAME
            attr = curses.color_pair(C_GREEN) | curses.A_BOLD if active else curses.color_pair(C_DIM)
            marker = "▶ " if active else "  "
            safe_addstr(win, y, 2, f"{marker}{name:<14} {role[:w-20]}", attr)

    draw_panel_border(win, focused)
    win.noutrefresh()

# ── Help page ─────────────────────────────────────────────────────────────────
_HELP = [
    ("Navigation",  [
        ("Tab",         "Cycle focus: none → left → right → none"),
        ("← →",        "Switch pages (when no panel focused)"),
        ("← →",        "Move between card columns (right panel)"),
        ("↑ ↓",        "Scroll log (left panel)"),
        ("↑ ↓",        "Navigate rows (right panel)"),
        ("1 - 9",      "Jump directly to page"),
        ("Enter",      "Expand selected item"),
        ("Esc",        "Collapse / unfocus panel"),
    ]),
    ("System",  [
        ("r",          "Force data refresh"),
        ("/",          "Search (Knowledge page)"),
        ("q",          "Quit"),
    ]),
    ("Pages",  [
        ("1",          "Overview — system card grid"),
        ("2",          "Kart — task queue"),
        ("3",          "Yggdrasil — local SLM models"),
        ("4",          "Knowledge — KB search"),
        ("5",          "Secrets — credential vault"),
        ("6",          "Agents — SAFE manifests"),
        ("7",          "Logs — full activity log"),
        ("8",          "Settings — configuration"),
        ("9",          "Help — this page"),
    ]),
]

def draw_help_left(win):
    win.erase()
    content_y = draw_willow_hero(win)
    safe_addstr(win, content_y,     2, "Help", curses.color_pair(C_HEADER) | curses.A_BOLD)
    safe_addstr(win, content_y + 1, 2, "Willow Terminal Dashboard", curses.color_pair(C_DIM))
    safe_addstr(win, content_y + 2, 2, "b17: DASH2  ΔΣ=42", curses.color_pair(C_DIM) | curses.A_DIM)
    draw_stat_strip(win)
    draw_panel_border(win, NAV.focus == "left")
    win.noutrefresh()

def draw_help_right(win):
    h, w = win.getmaxyx()
    win.erase()
    safe_addstr(win, 0, 1, "Keyboard Reference", curses.color_pair(C_HEADER) | curses.A_BOLD)
    y = 1
    for section, entries in _HELP:
        if y >= h - 1: break
        safe_addstr(win, y, 1, f"── {section} ──", curses.color_pair(C_AMBER) | curses.A_BOLD)
        y += 1
        for key, desc in entries:
            if y >= h - 1: break
            safe_addstr(win, y, 3, f"{key:<12}", curses.color_pair(C_BLUE) | curses.A_BOLD)
            safe_addstr(win, y, 16, desc[:w-17], curses.color_pair(C_DIM))
            y += 1
        y += 1
    draw_panel_border(win, NAV.focus == "right")
    win.noutrefresh()

# ── Main ──────────────────────────────────────────────────────────────────────
PAGE_DRAWS = {
    PAGE_OVERVIEW:  (draw_overview_left,   draw_overview_right),
    PAGE_KART:      (draw_kart_left,       draw_kart_right),
    PAGE_YGGDRASIL: (draw_yggdrasil_left,  draw_yggdrasil_right),
    PAGE_KNOWLEDGE: (draw_knowledge_left,  draw_knowledge_right),
    PAGE_SECRETS:   (draw_secrets_left,    draw_secrets_right),
    PAGE_AGENTS:    (draw_agents_left,     draw_agents_right),
    PAGE_SETTINGS:  (draw_settings_left,   draw_settings_right),
    PAGE_HELP:      (draw_help_left,       draw_help_right),
}

_NUKE_PLACARD = [
    "",
    "╔" + "═" * 71 + "╗",
    "║" + " " * 71 + "║",
    "║                        ▲  IRREVERSIBLE ACTION  ▲                       ║",
    "║" + " " * 71 + "║",
    "╠" + "═" * 71 + "╣",
    "║" + " " * 71 + "║",
    "║  WHAT WILL BE DESTROYED" + " " * 46 + "║",
    "║  ───────────────────────" + " " * 46 + "║",
    "║    • All atoms in ~/.willow/store/" + " " * 36 + "║",
    "║    • All sessions in willow.sap_sessions" + " " * 29 + "║",
    "║    • All LOAM atoms in willow_19" + " " * 37 + "║",
    "║    • FRANK's ledger chain from genesis" + " " * 32 + "║",
    "║    • Grove messages in this database" + " " * 33 + "║",
    "║" + " " * 71 + "║",
    "║  WHAT WILL BE PRESERVED" + " " * 46 + "║",
    "║  ──────────────────────" + " " * 47 + "║",
    "║    • Your SSH keys" + " " * 51 + "║",
    "║    • Your GPG keys" + " " * 51 + "║",
    "║    • Your Postgres cluster (only the willow_19 database is dropped)   ║",
    "║    • Files outside ~/.willow/" + " " * 40 + "║",
    "║" + " " * 71 + "║",
    "║  There is no undo. There is no recovery. There is no backup this      ║",
    "║  script is quietly keeping for you." + " " * 34 + "║",
    "║" + " " * 71 + "║",
    "║  To proceed, type:   I UNDERSTAND" + " " * 36 + "║",
    "║  To abort, press:    Esc" + " " * 45 + "║",
    "║" + " " * 71 + "║",
    "",   # input line — rendered dynamically
    "║" + " " * 71 + "║",
    "╚" + "═" * 71 + "╝",
    "",
]


def draw_nuke_placard(stdscr, input_so_far: str) -> None:
    """Full-screen nuke confirmation placard. Takes the whole screen."""
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    lines = list(_NUKE_PLACARD)
    # Build input line: fixed width, cursor at end
    typed = input_so_far[:40]
    input_line = f"║  > {typed}_" + " " * max(0, 64 - len(typed)) + "║"
    lines[-4] = input_line   # replace the empty placeholder
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


def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    skins.init(stdscr)
    _load_cards()
    threading.Thread(target=card_mod.refresh_card_values, args=(_CARDS,), daemon=True).start()

    stop_evt = threading.Event()
    t = threading.Thread(target=background_refresh, args=(stop_evt,), daemon=True)
    t.start()

    left_win = right_win = None

    def rebuild():
        nonlocal left_win, right_win
        h, w = stdscr.getmaxyx()
        left_w  = max(20, (w * 2) // 3)
        right_w = w - left_w
        left_win  = curses.newwin(h - 2, left_w,  1, 0)
        right_win = curses.newwin(h - 2, right_w, 1, left_w)

    rebuild()

    try:
        while True:
            key = stdscr.getch()

            # ── Nuke placard mode ─────────────────────────────────────────
            if NAV.nuke_mode:
                if key == 27:                        # Esc — abort
                    NAV.nuke_mode  = False
                    NAV.nuke_input = ""
                elif key in (curses.KEY_BACKSPACE, 127):
                    NAV.nuke_input = NAV.nuke_input[:-1]
                elif 32 <= key <= 126:
                    NAV.nuke_input += chr(key)
                    if NAV.nuke_input == "I UNDERSTAND":
                        DATA.push_log("nuke: confirmed — not implemented yet")
                        NAV.nuke_mode  = False
                        NAV.nuke_input = ""
                draw_nuke_placard(stdscr, NAV.nuke_input)
                continue

            # ── Chat input mode (overview left panel) ──
            if NAV.focus == "left" and NAV.page == PAGE_OVERVIEW and not NAV.searching:
                if key == 27:                        # Esc — unfocus
                    NAV.focus = None
                    with CHAT.lock: CHAT.input = ""
                    continue
                elif key in (curses.KEY_ENTER, 10, 13):
                    with CHAT.lock:
                        msg = CHAT.input.strip()
                        CHAT.input = ""
                    if msg and not CHAT.waiting:
                        threading.Thread(target=send_chat, args=(msg,), daemon=True).start()
                    continue
                elif key in (curses.KEY_BACKSPACE, 127):
                    with CHAT.lock: CHAT.input = CHAT.input[:-1]
                    continue
                elif key == 9:                       # Tab — move focus to right panel
                    NAV.tab()
                    continue
                elif key == ord('q'):                # Let qq quit even from chat mode
                    pass
                elif 32 <= key <= 126:
                    with CHAT.lock: CHAT.input += chr(key)
                    continue

            # ── Expanded card action keys ──
            if (NAV.expanded and NAV.focus == "right"
                    and NAV.page == PAGE_OVERVIEW
                    and 0 <= NAV.card_idx < len(_CARDS)):
                card = _CARDS[NAV.card_idx]
                if NAV.confirm_action:
                    if key in (ord('y'), curses.KEY_ENTER, 10, 13):
                        act = NAV.confirm_action
                        NAV.confirm_action = None
                        threading.Thread(target=_execute_confirm,
                                         args=(card, act, _get_expand_row(card)),
                                         daemon=True).start()
                    elif key in (ord('n'), 27):
                        NAV.confirm_action = None
                    continue
                else:
                    for action in card.actions:
                        if key == ord(action["key"]):
                            _dispatch_action(card, action)
                            continue

            # ── Search mode ──
            if NAV.searching:
                if key == 27:                        # Esc
                    NAV.searching = False
                elif key in (curses.KEY_ENTER, 10, 13):
                    NAV.searching = False
                elif key in (curses.KEY_BACKSPACE, 127):
                    NAV.search = NAV.search[:-1]
                elif 32 <= key <= 126:
                    NAV.search += chr(key)
            else:
                # ── Global keys ──
                if key == ord('q'):
                    if NAV.quit_confirm:
                        if shutdown_mod.SHUTDOWN.active and not shutdown_mod.SHUTDOWN.complete:
                            # Shutdown running — second q force-quits
                            break
                        elif not shutdown_mod.SHUTDOWN.active:
                            # Initiate graceful shutdown
                            shutdown_mod.initiate_shutdown(send_chat)
                            NAV.quit_confirm = False
                            NAV.focus = "left"
                        else:
                            break  # shutdown complete — exit
                    else:
                        NAV.quit_confirm = True
                elif NAV.quit_confirm and key != -1:
                    NAV.quit_confirm = False

                # Exit once shutdown completes
                if shutdown_mod.is_complete():
                    break
                if key == ord('r') and not NAV.quit_confirm:
                    threading.Thread(target=refresh_all, daemon=True).start()
                    threading.Thread(target=_load_cards, daemon=True).start()
                    DATA.push_log("manual refresh")
                elif key == ord('n') and not NAV.nuke_mode:
                    NAV.nuke_mode  = True
                    NAV.nuke_input = ""
                    continue
                elif key == ord('/'):
                    NAV.searching = True; NAV.search = ""
                elif key == 9:                        # Tab — cycle focus
                    NAV.tab()
                elif key == 27:                       # Esc
                    if NAV.expanded:
                        # Write session atom then collapse
                        if (NAV.page == PAGE_OVERVIEW and
                                0 <= NAV.card_idx < len(_CARDS)):
                            card = _CARDS[NAV.card_idx]
                            threading.Thread(target=_write_session_atom,
                                             args=(card,), daemon=True).start()
                            _persist_card_history(card.id,
                                CHAT.card_histories.get(card.id, []))
                            CHAT.set_context(None)
                        NAV.expanded = False
                    else:
                        NAV.focus = None
                elif key in (curses.KEY_ENTER, 10, 13):
                    if NAV.focus == "right" and NAV.page == PAGE_OVERVIEW:
                        if NAV.card_idx >= len(_CARDS):
                            # + card — enter creation mode, seed interview prompt
                            NAV.creating_card = True
                            with CHAT.lock:
                                CHAT.input = ""
                            threading.Thread(
                                target=send_chat,
                                args=("I'd like to add a new card to my dashboard.",),
                                daemon=True,
                            ).start()
                            NAV.focus = "left"
                        else:
                            expanding = not NAV.expanded
                            NAV.expanded  = expanding
                            NAV.expand_row = 0
                            card = _CARDS[NAV.card_idx]
                            if expanding:
                                CHAT.set_context(card.id)
                            else:
                                threading.Thread(target=_write_session_atom,
                                                 args=(card,), daemon=True).start()
                                _persist_card_history(card.id,
                                    CHAT.card_histories.get(card.id, []))
                                CHAT.set_context(None)
                    elif NAV.focus == "right" and NAV.page == PAGE_SETTINGS:
                        if NAV.card_idx >= _CATALOG_IDX_OFFSET:
                            cat_i = NAV.card_idx - _CATALOG_IDX_OFFSET
                            if 0 <= cat_i < len(_CATALOG_SEEDS):
                                seed = _CATALOG_SEEDS[cat_i]
                                rec  = soil.get("willow-dashboard/cards", seed.id)
                                c    = card_mod.CardDef.from_dict(rec) if rec else card_mod.CardDef.from_dict(seed.to_dict())
                                c.enabled = not c.enabled
                                card_mod.save_card(c)
                                threading.Thread(target=_load_cards, daemon=True).start()
                        elif NAV.card_idx >= _SKIN_IDX_OFFSET:
                            skin_i = NAV.card_idx - _SKIN_IDX_OFFSET
                            if 0 <= skin_i < len(skins.SKIN_SEEDS):
                                chosen = skins.SKIN_SEEDS[skin_i]
                                skins.set_active(chosen.id)
                                skins.ACTIVE = chosen
                                skins._apply_colors(chosen)
                            elif skin_i == len(skins.SKIN_SEEDS):
                                shutdown_mod.SHUTDOWN.raw_mode = not shutdown_mod.SHUTDOWN.raw_mode
                    else:
                        NAV.expanded = not NAV.expanded
                elif key == curses.KEY_RESIZE:
                    stdscr.clear(); rebuild()

                # ── Direct page jump (always works) ──
                elif ord('1') <= key <= ord('9'):
                    NAV.page = key - ord('1')
                    NAV.card_idx = 0; NAV.expanded = False; NAV.scroll = 0

                # ── Panel-aware arrow keys ──
                elif key == curses.KEY_UP:
                    if NAV.focus == "left" or NAV.page == PAGE_LOGS:
                        NAV.scroll = max(0, NAV.scroll - 1)
                    elif NAV.focus == "right":
                        if NAV.expanded:
                            NAV.expand_row = max(0, NAV.expand_row - 1)
                        elif NAV.page == PAGE_SETTINGS:
                            NAV.card_idx = max(0, NAV.card_idx - 1)
                        else:
                            gcols = skins.ACTIVE.grid_columns
                            NAV.card_idx = max(0, NAV.card_idx - gcols)

                elif key == curses.KEY_DOWN:
                    if NAV.focus == "left" or NAV.page == PAGE_LOGS:
                        with DATA.lock: total = len(DATA.log)
                        NAV.scroll = min(max(0, total - 1), NAV.scroll + 1)
                    elif NAV.focus == "right":
                        if NAV.expanded:
                            limit = getattr(NAV, "_expand_total", 0)
                            NAV.expand_row = min(max(0, limit - 1), NAV.expand_row + 1)
                        elif NAV.page == PAGE_SETTINGS:
                            top = _CATALOG_IDX_OFFSET + len(_CATALOG_SEEDS) - 1
                            NAV.card_idx = min(top, NAV.card_idx + 1)
                        else:
                            gcols = skins.ACTIVE.grid_columns
                            top = len(_CARDS)  # max valid idx is + card
                            NAV.card_idx = min(top, NAV.card_idx + gcols)

                elif key == curses.KEY_LEFT:
                    if NAV.focus == "right" and not NAV.expanded:
                        gcols = skins.ACTIVE.grid_columns
                        if NAV.card_idx % gcols > 0:
                            NAV.card_idx -= 1
                    elif NAV.focus is None:
                        NAV.page = (NAV.page - 1) % len(PAGE_NAMES)
                        NAV.card_idx = 0; NAV.expanded = False; NAV.scroll = 0

                elif key == curses.KEY_RIGHT:
                    if NAV.focus == "right" and not NAV.expanded:
                        gcols = skins.ACTIVE.grid_columns
                        top = len(_CARDS)
                        if NAV.card_idx % gcols < gcols - 1 and NAV.card_idx < top:
                            NAV.card_idx += 1
                    elif NAV.focus is None:
                        NAV.page = (NAV.page + 1) % len(PAGE_NAMES)
                        NAV.card_idx = 0; NAV.expanded = False; NAV.scroll = 0

            # ── Draw ──
            h, w = stdscr.getmaxyx()
            if h < 12 or w < 40:
                stdscr.erase()
                try: stdscr.addstr(0, 0, "terminal too small — resize to 80×24 or larger")
                except curses.error: pass
                stdscr.noutrefresh(); curses.doupdate()
                continue

            # cursor visible only when typing in chat
            chat_active = NAV.focus == "left" and NAV.page == PAGE_OVERVIEW
            try: curses.curs_set(2 if chat_active else 0)
            except curses.error: pass

            stdscr.erase()
            draw_title_bar(stdscr)
            draw_page_bar(stdscr)
            stdscr.noutrefresh()

            if NAV.page == PAGE_LOGS:
                draw_logs_full(left_win, right_win)
            else:
                draw_l, draw_r = PAGE_DRAWS[NAV.page]
                draw_l(left_win)
                draw_r(right_win)

            curses.doupdate()

    finally:
        stop_evt.set()

if __name__ == "__main__":
    import boot as _boot
    if "--skip-boot" not in sys.argv:
        if "--force-setup" in sys.argv:
            _boot.BOOT_CONFIG.unlink(missing_ok=True)
        boot_cfg = _boot.boot()
        if boot_cfg is None:
            sys.exit(0)
        if boot_cfg.get("agent_name"):
            os.environ.setdefault("WILLOW_AGENT_NAME", boot_cfg["agent_name"])
    curses.wrapper(main)
