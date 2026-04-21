"""boot.py — Pre-dashboard boot sequence for Willow Dashboard.
b17: WDASH  ΔΣ=42

Handles on every launch:
  Page 0  — environment check (all users)
  Auth    — GPG passphrase login (returning) or key creation (new)

New users additionally see:
  Page 1  — welcome / Heimdallr hero
  Page 2  — the covenant  (data + privacy)
  Page 3  — legal         (MIT + §1.1)
  Page 4  — path select   (professional / casual / novice)

Writes ~/.willow/willow-dashboard-boot.json on completion.
Called from dashboard.py before curses main loop.
"""
import curses
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ── Boot config location ─────────────────────────────────────────────────────
BOOT_CONFIG = Path.home() / ".willow" / "willow-dashboard-boot.json"

# ── Typewriter timing ────────────────────────────────────────────────────────
CHAR_DELAY  = 0.007   # 7ms per character
LINE_DELAY  = 0.08    # pause after each line
PAGE_PAUSE  = 0.4     # pause before "press any key"

# ── Amber phosphor color indices ─────────────────────────────────────────────
_CA_AMBER  = 1   # amber — primary text
_CA_DIM    = 2   # dim amber — secondary
_CA_GREEN  = 3   # confirmation green
_CA_RED    = 4   # error / missing
_CA_BRIGHT = 5   # bright white — headings
_CA_BOX    = 6   # box border


def _init_boot_colors():
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    amber  = 214 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    dim_a  = 130 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    curses.init_pair(_CA_AMBER,  amber,              -1)
    curses.init_pair(_CA_DIM,    dim_a,              -1)
    curses.init_pair(_CA_GREEN,  curses.COLOR_GREEN, -1)
    curses.init_pair(_CA_RED,    curses.COLOR_RED,   -1)
    curses.init_pair(_CA_BRIGHT, curses.COLOR_WHITE, -1)
    curses.init_pair(_CA_BOX,    dim_a,              -1)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _safe(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    try:
        win.addstr(y, x, text[:max(0, w - x - 1)], attr)
    except curses.error:
        pass


def _typewrite(win, y, x, text, attr=0, delay=CHAR_DELAY):
    """Print text character by character with a delay."""
    h, w = win.getmaxyx()
    cx = x
    for ch in text:
        if cx >= w - 1:
            break
        try:
            win.addch(y, cx, ch, attr)
            win.refresh()
        except curses.error:
            pass
        cx += 1
        time.sleep(delay)


def _typewrite_lines(win, start_y, x, lines, attr=0, delay=CHAR_DELAY):
    """Typewrite a list of lines, returning the last y used."""
    y = start_y
    h, _ = win.getmaxyx()
    for line in lines:
        if y >= h - 1:
            break
        _typewrite(win, y, x, line, attr, delay)
        y += 1
        time.sleep(LINE_DELAY)
    return y


def _draw_box(win, y, x, h, w, attr=0):
    try:
        win.attron(attr)
        win.addstr(y,         x, "┌" + "─" * (w - 2) + "┐")
        win.addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘")
        for row in range(1, h - 1):
            win.addstr(y + row, x,         "│")
            win.addstr(y + row, x + w - 1, "│")
        win.attroff(attr)
    except curses.error:
        pass


def _wait_key(win, prompt="  Press any key to continue...", y=None):
    h, w = win.getmaxyx()
    if y is None:
        y = h - 2
    time.sleep(PAGE_PAUSE)
    _safe(win, y, 2, prompt, curses.color_pair(_CA_DIM))
    win.refresh()
    win.nodelay(False)
    k = win.getch()
    win.nodelay(True)
    return k


def _fill_bg(win):
    """Fill background with black."""
    h, w = win.getmaxyx()
    win.bkgd(' ', curses.color_pair(_CA_AMBER))
    win.erase()


# ── Heimdallr ASCII art ───────────────────────────────────────────────────────
_HEIMDALLR_ART = [
    r"          )  (          ",
    r"         (    )         ",
    r"        ) \  / (        ",
    r"       /  (())  \       ",
    r"      | ·  \/  · |      ",
    r"      |   (  )   |      ",
    r"       \   \/   /       ",
    r"        \  /\  /        ",
    r"    ====/ /  \ \====    ",
    r"        | |  | |        ",
    r"       /| |  | |\       ",
    r"      /_|_|  |_|_\      ",
    r"    ~~~~~  \/  ~~~~~    ",
]

_WILLOW_WORDMARK = [
    r" ██╗    ██╗██╗██╗      ██╗      ██████╗ ██╗    ██╗",
    r" ██║    ██║██║██║      ██║     ██╔═══██╗██║    ██║",
    r" ██║ █╗ ██║██║██║      ██║     ██║   ██║██║ █╗ ██║",
    r" ██║███╗██║██║██║      ██║     ██║   ██║██║███╗██║",
    r" ╚███╔███╔╝██║███████╗ ███████╗╚██████╔╝╚███╔███╔╝",
    r"  ╚══╝╚══╝ ╚═╝╚══════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝",
]


# ── Environment detection ─────────────────────────────────────────────────────

def check_environment() -> dict:
    """Probe each subsystem. Returns {name: (status, detail)}."""
    results = {}

    # Postgres / LOAM
    try:
        import psycopg2
        dsn = os.environ.get("WILLOW_DB_URL", "")
        if dsn:
            conn = psycopg2.connect(dsn, connect_timeout=3)
        else:
            conn = psycopg2.connect(
                dbname=os.environ.get("WILLOW_PG_DB", "willow"),
                user=os.environ.get("WILLOW_PG_USER", os.environ.get("USER", "")),
                connect_timeout=3,
            )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.knowledge")
        count = cur.fetchone()[0]
        conn.close()
        results["LOAM / POSTGRES"] = ("ok", f"{count:,} atoms")
    except Exception as e:
        results["LOAM / POSTGRES"] = ("missing", str(e)[:40])

    # Ollama
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        ygg = sorted([m for m in models if "yggdrasil" in m.lower()], reverse=True)
        ver = ygg[0].split(":")[-1] if ygg else "no yggdrasil"
        results["OLLAMA"] = ("ok", f"{len(models)} models · yggdrasil:{ver}")
    except Exception:
        results["OLLAMA"] = ("missing", "unreachable")

    # SAFE
    safe_root = os.environ.get("WILLOW_SAFE_ROOT",
                str(Path.home() / "SAFE_backup" / "Applications"))
    if Path(safe_root).is_dir():
        apps = [d for d in Path(safe_root).iterdir() if d.is_dir()]
        results["SAFE"] = ("ok", f"{len(apps)} manifests at {safe_root}")
    else:
        results["SAFE"] = ("missing", "WILLOW_SAFE_ROOT not found")

    # SOIL
    store_root = Path(os.environ.get("WILLOW_STORE_ROOT",
                      str(Path.home() / ".willow" / "store")))
    if store_root.exists():
        collections = list(store_root.rglob("store.db"))
        results["SOIL"] = ("ok", f"{len(collections)} collections")
    else:
        results["SOIL"] = ("missing", "store not initialised")

    # MCP
    mcp_file = Path.cwd() / ".mcp.json"
    if mcp_file.exists():
        try:
            data = json.loads(mcp_file.read_text())
            n = len(data.get("mcpServers", {}))
            results["MCP"] = ("ok", f"{n} servers")
        except Exception:
            results["MCP"] = ("warn", "config unreadable")
    else:
        results["MCP"] = ("missing", "no .mcp.json")

    # GPG
    fp = _load_boot_config().get("pgp_fingerprint", "")
    if fp:
        results["GPG IDENTITY"] = ("ok", f"{fp[:16]}...")
    else:
        results["GPG IDENTITY"] = ("missing", "no key registered")

    return results


# ── Boot config ───────────────────────────────────────────────────────────────

def _load_boot_config() -> dict:
    if BOOT_CONFIG.exists():
        try:
            return json.loads(BOOT_CONFIG.read_text())
        except Exception:
            pass
    return {}


def _save_boot_config(cfg: dict) -> None:
    BOOT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    BOOT_CONFIG.write_text(json.dumps(cfg, indent=2, default=str))


def needs_boot() -> bool:
    cfg = _load_boot_config()
    return not cfg.get("completed", False)


# ── GPG helpers ───────────────────────────────────────────────────────────────

def _gpg(args: list, input_text: str = "") -> tuple[int, str, str]:
    """Run gpg with given args. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--yes"] + args,
            input=input_text.encode() if input_text else None,
            capture_output=True,
            timeout=30,
        )
        return result.returncode, result.stdout.decode(), result.stderr.decode()
    except Exception as e:
        return 1, "", str(e)


def gpg_list_keys() -> list[dict]:
    """List secret keys. Returns [{fingerprint, uid, created}]."""
    rc, out, _ = _gpg(["--list-secret-keys", "--with-colons", "--with-fingerprint"])
    keys = []
    current = {}
    for line in out.splitlines():
        parts = line.split(":")
        if parts[0] == "sec":
            current = {"fingerprint": "", "uid": "", "created": parts[5] if len(parts) > 5 else ""}
        elif parts[0] == "fpr" and current is not None:
            current["fingerprint"] = parts[9] if len(parts) > 9 else ""
        elif parts[0] == "uid" and current is not None:
            current["uid"] = parts[9] if len(parts) > 9 else ""
            keys.append(dict(current))
    return keys


def gpg_create_key(name: str, email: str, passphrase: str) -> str:
    """Generate a new GPG key. Returns fingerprint or empty string on failure."""
    params = f"""%no-protection
Key-Type: RSA
Key-Length: 4096
Name-Real: {name}
Name-Email: {email}
Expire-Date: 0
Passphrase: {passphrase}
%commit
"""
    rc, out, err = _gpg(["--gen-key", "--status-fd", "1"], params)
    # Extract fingerprint from newly created key
    keys = gpg_list_keys()
    for k in keys:
        if email in k.get("uid", ""):
            return k["fingerprint"]
    return ""


def gpg_authenticate(fingerprint: str, passphrase: str) -> bool:
    """Sign a nonce with the given key. Returns True if passphrase is correct."""
    nonce = str(uuid.uuid4())
    nonce_file = Path("/tmp") / f"willow-auth-{uuid.uuid4().hex[:8]}"
    nonce_file.write_text(nonce)
    try:
        rc, out, err = _gpg([
            "--sign", "--armor",
            "--local-user", fingerprint,
            "--passphrase-fd", "0",
            "--pinentry-mode", "loopback",
            str(nonce_file),
        ], passphrase)
        return rc == 0
    finally:
        nonce_file.unlink(missing_ok=True)
        sig_file = Path(str(nonce_file) + ".asc")
        sig_file.unlink(missing_ok=True)


def gpg_agent_has_key(fingerprint: str) -> bool:
    """Check if gpg-agent already has the key unlocked (no passphrase needed)."""
    nonce = str(uuid.uuid4())
    nonce_file = Path("/tmp") / f"willow-agent-{uuid.uuid4().hex[:8]}"
    nonce_file.write_text(nonce)
    try:
        rc, _, _ = _gpg([
            "--sign", "--armor",
            "--local-user", fingerprint,
            "--pinentry-mode", "loopback",
            str(nonce_file),
        ])
        return rc == 0
    finally:
        nonce_file.unlink(missing_ok=True)
        Path(str(nonce_file) + ".asc").unlink(missing_ok=True)


# ── Pages ─────────────────────────────────────────────────────────────────────

def page_boot_check(win) -> dict:
    """Page 0 — environment probe. Shown to all users on every launch."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    green  = curses.color_pair(_CA_GREEN)  | curses.A_BOLD
    red    = curses.color_pair(_CA_RED)    | curses.A_BOLD
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD

    _typewrite(win, 1, 2, "WILLOW DASHBOARD", bright, delay=0.012)
    _safe(win, 2, 2, "─" * min(60, w - 4), dim)
    time.sleep(0.2)

    env = check_environment()
    y = 4
    col_name = 4
    col_dots = 26
    col_stat = col_dots + 6

    _typewrite(win, y, 2, "CHECKING ENVIRONMENT...", dim, delay=0.008)
    y += 2
    win.refresh()

    for name, (status, detail) in env.items():
        dots = "." * max(2, col_dots - col_name - len(name))
        _safe(win, y, col_name, name, amber)
        _safe(win, y, col_name + len(name) + 1, dots, dim)
        time.sleep(0.12)
        if status == "ok":
            stat_str = f"[ {detail} ]"
            _safe(win, y, col_stat, stat_str[:w - col_stat - 2], green)
        else:
            stat_str = f"[ {status.upper()} — {detail} ]"
            _safe(win, y, col_stat, stat_str[:w - col_stat - 2], red)
        win.refresh()
        y += 1

    y += 1
    all_ok = all(s == "ok" for s, _ in env.values())
    gpg_ok = env.get("GPG IDENTITY", ("missing",))[0] == "ok"

    _safe(win, y, 2, "─" * min(60, w - 4), dim)
    y += 1

    if all_ok:
        _typewrite(win, y, 2, "ALL SYSTEMS NOMINAL", green, delay=0.01)
    elif gpg_ok:
        _typewrite(win, y, 2, "PARTIAL — SOME SERVICES UNAVAILABLE", amber, delay=0.01)
    else:
        _typewrite(win, y, 2, "STANDALONE MODE", amber, delay=0.01)

    win.refresh()
    return env


def page_welcome(win):
    """Page 1 — Heimdallr hero. New users only."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD

    # ASCII art centered
    art_w = max(len(l) for l in _HEIMDALLR_ART)
    art_x = max(2, (w // 2) - (art_w // 2) - 10)
    for i, line in enumerate(_HEIMDALLR_ART):
        _safe(win, 2 + i, art_x, line, amber)
    win.refresh()
    time.sleep(0.3)

    # Wordmark if wide enough
    wm_x = max(2, (w // 2) + 2)
    if w > 90:
        for i, line in enumerate(_WILLOW_WORDMARK):
            _safe(win, 4 + i, wm_x, line[:w - wm_x - 2], bright)
        text_y = 13
    else:
        _safe(win, 4, wm_x, "W I L L O W", bright)
        text_y = 7

    win.refresh()
    time.sleep(0.4)

    # Intro text — typewritten
    intro = [
        "",
        "  A personal terminal workspace.",
        "  Built on your machine.",
        "  Answerable only to you.",
        "",
        "  I am HEIMDALLR.",
        "  I watch the bridge between",
        "  what you know and what you're building.",
        "",
        "  Before we begin — a few things.",
    ]
    _typewrite_lines(win, text_y, art_x, intro, dim)
    _wait_key(win)


def page_covenant(win):
    """Page 2 — data privacy covenant. New users only."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD
    green  = curses.color_pair(_CA_GREEN)

    _typewrite(win, 1, 2, "WHAT THIS SYSTEM KNOWS ABOUT YOU", bright, delay=0.01)
    _safe(win, 2, 2, "─" * min(60, w - 4), curses.color_pair(_CA_DIM))
    time.sleep(0.2)

    lines = [
        "",
        "  This system can track a lot.",
        "  Your projects. Your notes. Your habits.",
        "  Your conversations. Your work history.",
        "",
        "  That is the whole point.",
        "",
        "  But here is what makes this different:",
        "",
    ]
    y = _typewrite_lines(win, 3, 2, lines, dim)

    covenants = [
        ("  Everything lives here.",   "On this machine. Nowhere else."),
        ("  Nothing phones home.",      "No telemetry. No analytics. No cloud."),
        ("  You choose what to track.", "Every data type requires your consent."),
        ("  You own the data.",         "Delete it, export it, or ignore it."),
    ]

    for title, sub in covenants:
        if y >= h - 4:
            break
        _typewrite(win, y, 2, title, amber)
        y += 1
        _safe(win, y, 4, sub, dim)
        y += 2
        win.refresh()
        time.sleep(0.1)

    _wait_key(win)


def page_legal(win) -> bool:
    """Page 3 — MIT + §1.1. Returns True if agreed, False if quit."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD
    green  = curses.color_pair(_CA_GREEN)  | curses.A_BOLD
    red    = curses.color_pair(_CA_RED)

    box_h, box_w = min(18, h - 4), min(62, w - 4)
    box_x = max(2, (w - box_w) // 2)
    box_y = 2

    _draw_box(win, box_y, box_x, box_h, box_w, curses.color_pair(_CA_BOX))

    content_x = box_x + 3
    y = box_y + 1

    _typewrite(win, y, content_x, "TERMS OF USE", bright, delay=0.01)
    y += 1
    _safe(win, y, content_x, "─" * (box_w - 6), curses.color_pair(_CA_DIM))
    y += 2

    terms = [
        ("This software is free.", dim),
        ("Use it. Learn from it. Build with it.", dim),
        ("", dim),
        ("If you make money with it —", amber),
        ("that is a conversation worth having.", amber),
        ("", dim),
        ("Personal use:     always free.", dim),
        ("Commercial use:   written consent required.", dim),
        ("                  rudi193@gmail.com", dim),
        ("", dim),
        ("MIT License · Copyright 2026 Sean Campbell", dim),
        ("§ 1.1 Commercial Consent Clause", dim),
    ]

    for text, attr in terms:
        if y >= box_y + box_h - 3:
            break
        if text:
            _typewrite(win, y, content_x, text, attr, delay=0.004)
        y += 1
        win.refresh()

    # Prompt
    prompt_y = box_y + box_h - 2
    _safe(win, prompt_y, content_x, "[ Y ] I understand and agree", green)
    _safe(win, prompt_y, content_x + 32, "[ Q ] Quit", red)
    win.refresh()

    win.nodelay(False)
    while True:
        k = win.getch()
        if k in (ord('y'), ord('Y')):
            win.nodelay(True)
            return True
        if k in (ord('q'), ord('Q'), 27):
            win.nodelay(True)
            return False


def page_path_select(win) -> str:
    """Page 4 — Professional / Casual / Novice. Returns path string."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD
    green  = curses.color_pair(_CA_GREEN)  | curses.A_BOLD

    _typewrite(win, 1, 2, "HOW DO YOU WORK?", bright, delay=0.01)
    _safe(win, 2, 2, "─" * min(60, w - 4), dim)
    time.sleep(0.2)

    paths = [
        ("1", "PROFESSIONAL",
         "I know what I'm doing. Show me everything.",
         "Full config. All cards. Technical detail.", "professional"),
        ("2", "CASUAL",
         "Guide me through it. Plain English is fine.",
         "Guided setup. Curated card set. Simple language.", "casual"),
        ("3", "NEW HERE",
         "I'm new to this kind of tool. Take it slow.",
         "Step by step. Explain as we go. Minimal config.", "novice"),
    ]

    y = 4
    for key, title, desc, sub, _ in paths:
        _safe(win, y, 4, f"[ {key} ]", amber)
        _safe(win, y, 10, title, bright)
        y += 1
        _safe(win, y, 10, desc, dim)
        y += 1
        _safe(win, y, 10, sub, curses.color_pair(_CA_DIM))
        y += 2
        win.refresh()
        time.sleep(0.05)

    win.nodelay(False)
    while True:
        k = win.getch()
        for key, title, desc, sub, path in paths:
            if k == ord(key):
                _safe(win, h - 2, 2, f"  Path: {title}", green)
                win.refresh()
                time.sleep(0.4)
                win.nodelay(True)
                return path


def page_pgp_create(win) -> str:
    """PGP key creation for new users. Returns fingerprint."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD
    green  = curses.color_pair(_CA_GREEN)  | curses.A_BOLD
    red    = curses.color_pair(_CA_RED)

    _typewrite(win, 1, 2, "CREATING YOUR IDENTITY", bright, delay=0.01)
    _safe(win, 2, 2, "─" * min(60, w - 4), dim)
    time.sleep(0.2)

    intro = [
        "",
        "  A GPG key pair will be generated on this machine.",
        "  Your private key never leaves here.",
        "  Your fingerprint identifies you to the Willow system.",
        "",
    ]
    y = _typewrite_lines(win, 2, 2, intro, dim)
    win.refresh()

    def _get_input(prompt_y, label):
        _safe(win, prompt_y, 4, label, amber)
        curses.curs_set(1)
        curses.echo()
        win.nodelay(False)
        _safe(win, prompt_y, 4 + len(label) + 1, " " * 40, dim)
        win.move(prompt_y, 4 + len(label) + 1)
        val = win.getstr(40).decode().strip()
        curses.noecho()
        curses.curs_set(0)
        return val

    def _get_password(prompt_y, label):
        _safe(win, prompt_y, 4, label, amber)
        curses.curs_set(1)
        win.nodelay(False)
        win.keypad(True)
        _safe(win, prompt_y, 4 + len(label) + 1, " " * 40, dim)
        win.move(prompt_y, 4 + len(label) + 1)
        pwd = ""
        cx = 4 + len(label) + 1
        while True:
            k = win.getch()
            if k in (curses.KEY_ENTER, 10, 13):
                break
            elif k in (curses.KEY_BACKSPACE, 127):
                if pwd:
                    pwd = pwd[:-1]
                    cx -= 1
                    _safe(win, prompt_y, cx, " ", dim)
                    win.move(prompt_y, cx)
            elif 32 <= k <= 126:
                pwd += chr(k)
                _safe(win, prompt_y, cx, "*", amber)
                cx += 1
                win.move(prompt_y, cx)
            win.refresh()
        curses.curs_set(0)
        return pwd

    while True:
        name       = _get_input(y,     "Name ............. ")
        email      = _get_input(y + 1, "Email ............ ")
        passphrase = _get_password(y + 2, "Passphrase ....... ")
        confirm    = _get_password(y + 3, "Confirm .......... ")

        if passphrase != confirm:
            _safe(win, y + 5, 4, "Passphrases do not match. Try again.", red)
            win.refresh()
            time.sleep(1.5)
            _safe(win, y + 5, 4, " " * 40, dim)
            continue

        if len(passphrase) < 8:
            _safe(win, y + 5, 4, "Passphrase too short (min 8 chars). Try again.", red)
            win.refresh()
            time.sleep(1.5)
            _safe(win, y + 5, 4, " " * 50, dim)
            continue

        break

    _safe(win, y + 5, 4, "Generating key pair...", dim)
    win.refresh()

    fingerprint = gpg_create_key(name, email, passphrase)

    if fingerprint:
        _safe(win, y + 6, 4, "Key created.", green)
        _safe(win, y + 7, 4, f"Fingerprint: {fingerprint[:32]}...", dim)
        win.refresh()
        time.sleep(1.0)
    else:
        _safe(win, y + 6, 4, "Key generation failed. Check gpg is installed.", red)
        win.refresh()
        time.sleep(2.0)

    win.nodelay(True)
    return fingerprint


def page_pgp_auth(win, fingerprint: str, agent_name: str) -> bool:
    """Returning user auth. Returns True if authenticated."""
    _fill_bg(win)
    h, w = win.getmaxyx()
    amber  = curses.color_pair(_CA_AMBER)  | curses.A_BOLD
    dim    = curses.color_pair(_CA_DIM)
    bright = curses.color_pair(_CA_BRIGHT) | curses.A_BOLD
    green  = curses.color_pair(_CA_GREEN)  | curses.A_BOLD
    red    = curses.color_pair(_CA_RED)

    _typewrite(win, 1, 2, f"WELCOME BACK, {agent_name.upper()}", bright, delay=0.01)
    _safe(win, 2, 2, "─" * min(60, w - 4), dim)
    _safe(win, 4, 4, f"Fingerprint: {fingerprint[:32]}...", dim)
    win.refresh()
    time.sleep(0.2)

    # Try GPG agent first (no passphrase needed)
    _safe(win, 5, 4, "Checking GPG agent...", dim)
    win.refresh()
    if gpg_agent_has_key(fingerprint):
        _safe(win, 5, 4, "✓  AUTHENTICATED VIA GPG AGENT          ", green)
        win.refresh()
        time.sleep(0.8)
        return True

    _safe(win, 5, 4, "Enter passphrase to unlock.             ", dim)

    def _get_password(prompt_y):
        _safe(win, prompt_y, 4, "Passphrase ....... ", amber)
        curses.curs_set(1)
        win.nodelay(False)
        win.keypad(True)
        pwd = ""
        cx = 4 + 19
        win.move(prompt_y, cx)
        while True:
            k = win.getch()
            if k in (curses.KEY_ENTER, 10, 13):
                break
            elif k in (curses.KEY_BACKSPACE, 127):
                if pwd:
                    pwd = pwd[:-1]
                    cx -= 1
                    _safe(win, prompt_y, cx, " ", dim)
                    win.move(prompt_y, cx)
            elif k in (ord('q'), ord('Q'), 27):
                curses.curs_set(0)
                return None
            elif 32 <= k <= 126:
                pwd += chr(k)
                _safe(win, prompt_y, cx, "*", amber)
                cx += 1
                win.move(prompt_y, cx)
            win.refresh()
        curses.curs_set(0)
        return pwd

    attempts = 0
    while attempts < 3:
        passphrase = _get_password(7)
        if passphrase is None:
            win.nodelay(True)
            return False

        _safe(win, 9, 4, "Verifying...", dim)
        win.refresh()

        if gpg_authenticate(fingerprint, passphrase):
            _safe(win, 9, 4, "✓  AUTHENTICATED                        ", green)
            win.refresh()
            time.sleep(0.6)
            win.nodelay(True)
            return True
        else:
            attempts += 1
            remaining = 3 - attempts
            msg = f"Incorrect. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            _safe(win, 9, 4, msg, red)
            win.refresh()
            time.sleep(1.0)
            _safe(win, 9, 4, " " * 50, dim)
            _safe(win, 7, 4, "Passphrase ....... " + " " * 30, dim)

    win.nodelay(True)
    return False


# ── Main boot orchestrator ────────────────────────────────────────────────────

def run_boot(stdscr):
    """Full boot sequence. Returns completed boot config dict."""
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    _init_boot_colors()
    stdscr.bkgd(' ', curses.color_pair(_CA_AMBER))

    cfg = _load_boot_config()
    is_new = not cfg.get("completed", False)

    # ── Page 0: Environment check (everyone) ─────────────────────────────────
    env = page_boot_check(stdscr)

    if is_new:
        # ── New user path ─────────────────────────────────────────────────────
        _wait_key(stdscr)

        page_welcome(stdscr)
        page_covenant(stdscr)

        agreed = page_legal(stdscr)
        if not agreed:
            return None  # user quit at legal screen

        path = page_path_select(stdscr)

        fingerprint = page_pgp_create(stdscr)

        cfg = {
            "completed":     True,
            "first_run_at":  datetime.now().isoformat(),
            "path":          path,
            "pgp_fingerprint": fingerprint,
            "agreed_license":  True,
            "agreed_covenant": True,
            "agent_name":    os.environ.get("WILLOW_AGENT_NAME", "heimdallr"),
        }
        _save_boot_config(cfg)

        # Set env var for dashboard
        if fingerprint:
            os.environ["WILLOW_PGP_FINGERPRINT"] = fingerprint

    else:
        # ── Returning user: GPG auth then go ─────────────────────────────────
        fingerprint = cfg.get("pgp_fingerprint", "")
        agent_name  = cfg.get("agent_name",
                              os.environ.get("WILLOW_AGENT_NAME", "heimdallr"))

        if fingerprint:
            authenticated = page_pgp_auth(stdscr, fingerprint, agent_name)
            if not authenticated:
                return None  # failed auth — do not launch dashboard

            os.environ["WILLOW_PGP_FINGERPRINT"] = fingerprint
        else:
            # No key on record — prompt to create one
            _safe(stdscr, stdscr.getmaxyx()[0] - 3, 2,
                  "No identity found. Creating key...", curses.color_pair(_CA_AMBER))
            stdscr.refresh()
            time.sleep(1.0)
            fingerprint = page_pgp_create(stdscr)
            cfg["pgp_fingerprint"] = fingerprint
            cfg["last_boot_at"] = datetime.now().isoformat()
            _save_boot_config(cfg)
            if fingerprint:
                os.environ["WILLOW_PGP_FINGERPRINT"] = fingerprint

        # Update last boot timestamp
        cfg["last_boot_at"] = datetime.now().isoformat()
        _save_boot_config(cfg)

        # Brief pause then hand off
        h, w = stdscr.getmaxyx()
        _safe(stdscr, h - 2, 2, "  Loading dashboard...", curses.color_pair(_CA_GREEN))
        stdscr.refresh()
        time.sleep(0.6)

    return cfg


def boot() -> dict | None:
    """Entry point. Run the boot sequence. Returns config or None if aborted."""
    result = {}
    def _run(stdscr):
        nonlocal result
        result = run_boot(stdscr)
    curses.wrapper(_run)
    return result


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = boot()
    if cfg:
        print(f"Boot complete. Path: {cfg.get('path')}  FP: {cfg.get('pgp_fingerprint','none')[:16]}")
    else:
        print("Boot aborted.")
