"""skins.py — Skin system for the Willow Dashboard.
b17: WDASH  ΔΣ=42

Skins live in SOIL under willow-dashboard/skins.
Active skin ID is stored in willow-dashboard/config under key active_skin.
"""
import curses
from dataclasses import dataclass, field
from typing import Optional
import soil

# ── Color pair indices (same as dashboard.py) ────────────────────────────────
C_DEFAULT  = 0
C_BLUE     = 1
C_GREEN    = 2
C_AMBER    = 3
C_DIM      = 4
C_HEADER   = 5
C_PILL     = 6
C_RED      = 7
C_BROWN    = 8
C_SELECT   = 9
C_BORDER   = 10

# ── Accessible skin symbol map ────────────────────────────────────────────────
STATE_SYMBOLS = {"green": "✓", "amber": "▲", "red": "✗", "blue": "●", "dim": "·"}
SYMBOL_KEY    = "✓=ok  ▲=warn  ✗=err  ●=info"


@dataclass
class Skin:
    id: str
    label: str
    # Foreground color indices for curses.init_pair (0-7 standard, 0-255 256-color)
    color_header: int = curses.COLOR_WHITE
    color_value:  int = curses.COLOR_BLUE
    color_green:  int = curses.COLOR_GREEN
    color_amber:  int = curses.COLOR_YELLOW
    color_red:    int = curses.COLOR_RED
    color_dim:    int = curses.COLOR_WHITE
    color_pill:   int = curses.COLOR_CYAN
    color_select: int = curses.COLOR_CYAN
    color_border: int = curses.COLOR_WHITE
    color_hero:   int = curses.COLOR_GREEN
    # Layout
    grid_columns:   int  = 2
    left_width_pct: int  = 66
    border_style:   str  = "box"
    card_height:    int  = 4
    stat_strip:     bool = True
    # Accessibility flag — adds symbol prefix to card values
    accessible: bool = False
    # Extension stub
    custom: Optional[dict] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, d: dict) -> "Skin":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in valid})


# ── Seed definitions ──────────────────────────────────────────────────────────
SKIN_SEEDS: list[Skin] = [
    Skin(id="default",    label="Default",
         color_header=curses.COLOR_WHITE, color_value=curses.COLOR_BLUE,
         color_green=curses.COLOR_GREEN,  color_amber=curses.COLOR_YELLOW,
         color_hero=curses.COLOR_GREEN),

    Skin(id="midnight",   label="Midnight",
         color_header=curses.COLOR_MAGENTA, color_value=curses.COLOR_MAGENTA,
         color_green=curses.COLOR_GREEN,    color_amber=curses.COLOR_YELLOW,
         color_hero=curses.COLOR_GREEN),

    Skin(id="forest",     label="Forest",
         color_header=curses.COLOR_GREEN, color_value=curses.COLOR_GREEN,
         color_amber=curses.COLOR_YELLOW, color_hero=curses.COLOR_GREEN,
         color_pill=curses.COLOR_GREEN),

    Skin(id="amber",      label="Amber",
         color_header=curses.COLOR_YELLOW, color_value=curses.COLOR_YELLOW,
         color_green=curses.COLOR_YELLOW,  color_amber=curses.COLOR_YELLOW,
         color_dim=curses.COLOR_YELLOW,    color_pill=curses.COLOR_YELLOW,
         color_hero=curses.COLOR_YELLOW),

    Skin(id="accessible", label="High Contrast",
         color_header=curses.COLOR_WHITE, color_value=curses.COLOR_WHITE,
         color_green=curses.COLOR_WHITE,  color_amber=curses.COLOR_YELLOW,
         color_red=curses.COLOR_YELLOW,   color_dim=curses.COLOR_WHITE,
         color_hero=curses.COLOR_WHITE,   accessible=True),
]

_SKIN_MAP: dict[str, Skin] = {s.id: s for s in SKIN_SEEDS}

# Module-level active skin — set by init() at startup
ACTIVE: Skin = _SKIN_MAP["default"]


def seed() -> None:
    """Seed skin definitions to SOIL (safe to call multiple times)."""
    existing = {r["id"] for r in soil.all_records("willow-dashboard/skins")}
    for s in SKIN_SEEDS:
        if s.id not in existing:
            soil.put("willow-dashboard/skins", s.id, s.to_dict())


def load() -> Skin:
    """Load active skin from SOIL config. Falls back to default."""
    cfg = soil.get("willow-dashboard/config", "active_skin")
    skin_id = cfg.get("value", "default") if cfg else "default"
    rec = soil.get("willow-dashboard/skins", skin_id)
    if rec:
        return Skin.from_dict(rec)
    return _SKIN_MAP.get(skin_id, _SKIN_MAP["default"])


def set_active(skin_id: str) -> None:
    """Persist active skin choice to SOIL config."""
    soil.put("willow-dashboard/config", "active_skin", {"value": skin_id})


def init(stdscr=None) -> Skin:
    """Seed, load, apply colors. Call once at startup after curses init."""
    global ACTIVE
    seed()
    ACTIVE = load()
    if stdscr is not None:
        _apply_colors(ACTIVE)
    return ACTIVE


def _apply_colors(skin: Skin) -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_BLUE,    skin.color_value,  -1)
    curses.init_pair(C_GREEN,   skin.color_green,  -1)
    curses.init_pair(C_AMBER,   skin.color_amber,  -1)
    curses.init_pair(C_DIM,     skin.color_dim,    -1)
    curses.init_pair(C_HEADER,  skin.color_header, -1)
    curses.init_pair(C_PILL,    skin.color_pill,   -1)
    curses.init_pair(C_RED,     skin.color_red,    -1)
    curses.init_pair(C_SELECT,  skin.color_select, -1)
    curses.init_pair(C_BORDER,  skin.color_border, -1)
    brown = 130 if curses.COLORS >= 256 else curses.COLOR_YELLOW
    curses.init_pair(C_BROWN, brown, -1)
