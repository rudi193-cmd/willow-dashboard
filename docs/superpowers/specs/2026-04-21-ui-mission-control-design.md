# UI Redesign — Mission Control Aesthetic
b17: WDASH  ΔΣ=42

**Date:** 2026-04-21
**Scope:** Overview page + global chrome
**Approach:** Chrome-first — global shell improvements lift all pages, Overview gets structural redesign

---

## Aesthetic Direction

**Mission control.** Dense, information-rich, everything visible at a glance. Inspired by NASA ops rooms and htop. Color-coded status, live indicators, named instrument panels. Nothing hidden, nothing decorative that doesn't carry data.

The willow tree hero bar stays — it's unique and already works. All changes happen below it.

---

## Section 1: Global Chrome

Three changes applied across all pages.

### 1.1 Hero Footer Vitals Strip

The bottom edge of the hero bar (`draw_hline` call after the tree) becomes a live vitals strip:

```
─── CPU ████████░░ 78%  MEM ██████░░░░ 61%  TMP 44°C  DISK 42% ──────────
```

- Rendered as part of `_draw_hero()`
- Data sourced from the same system stats refresh cycle (30s interval)
- Uses `C_BLUE` for bar fill, `C_DIM` for empty bar segments, `C_AMBER | A_BOLD` for values that cross warning thresholds (CPU > 85%, TMP > 70°C)
- Falls back to `--` if stats unavailable

### 1.2 Section Header Helper

New function `_section_header(win, y, label)` — renders a full-width rule in the style:

```
── LABEL ────────────────────────────────────
```

Uses `C_BLUE | A_BOLD` for the label, `C_DIM` for the rule fill. Replaces all bare `safe_addstr` panel label calls across every page. Gives every panel a named instrument-panel header.

### 1.3 Page Nav Bar Contrast

Active page pill: `A_REVERSE | C_AMBER | A_BOLD`
Inactive pages: `C_DIM`

No structural change — just sharper contrast so the current location is unambiguous.

---

## Section 2: Overview Page Layout

The Overview page is restructured below the hero bar into two panels.

### Layout

```
┌─ W I L L O W ──── ☀ 09:14 ──── heimdallr ──── ● LIVE ──────────────────┐
│   [animated willow tree hero — unchanged]                                 │
│── CPU ████████░░ 78%  MEM ██████░░░░ 61%  TMP 44°C  DISK 42% ──────────│
├── COMMAND ──────────────────────────────────┬── STATUS ──────────────────┤
│                                             │                            │
│  heim: system nominal. all components       │ ● Postgres                 │
│        warm. vault sealed.                  │   68K atoms · 9ms          │
│                                             │ ▲ Kart                     │
│  you: any alerts?                           │   12q · 3r · 0f            │
│  heim: none. yggdrasil briefly degraded     │ ● Ollama                   │
│        01:44 ago — recovered.               │   ygg:v9 · warm            │
│                                             │ ● SAFE                     │
│                                             │   4 signed · ok            │
│                                             │ ● LOAM                     │
│                                             │   68K atoms · ok           │
│                                             │── VITALS ──────────────────│
│                                             │ CPU ████████░░ 78%         │
│                                             │ MEM ██████░░░░ 61%         │
│                                             │ TMP ████░░░░░░ 44°         │
│                                             │── QUEUE ───────────────────│
│  ▸ _                                        │ #4471 ingest     2h ago    │
│                                             │ #4472 journal    1h ago    │
└─────────────────────────────────────────────┴────────────────────────────┘
```

### Panel Split
- Left (COMMAND): ~65% of terminal width
- Right (STATUS): ~35% of terminal width
- Split point computed at render time from `stdscr.getmaxyx()`

### Left Panel — COMMAND

- Header: `_section_header(win, 0, "COMMAND")`
- Full scrollable conversation history
  - `heim:` lines: `C_BLUE`
  - `you:` lines: `C_DIM`
  - No truncation — scrolls with ↑↓ when panel is focused
- Separator line above input row
- Input row:
  - Active (panel focused): `▸ _` in `C_AMBER | A_BOLD`
  - Unfocused: `▸ ask heimdallr...` in `C_DIM | A_DIM`
- Streaming: `▌` appended to current heim response while Ollama generating

### Right Panel — STATUS

- Header: `_section_header(win, 0, "STATUS")`
- One entry per system, dot + inline metrics:
  - Status dot: `●` green (`C_GREEN`) = ok, `▲` amber (`C_AMBER`) = warn, `✗` red (`C_RED`) = error
  - System name on first line
  - Key metrics indented two spaces on second line, `C_DIM`
- Divider + `── VITALS ──` subsection:
  - CPU, MEM, TMP with ASCII progress bars (`████░░░░`)
  - Bar fill: `C_GREEN` below threshold, `C_AMBER` above
- Divider + `── QUEUE ──` subsection:
  - 3 most recent Kart tasks: `#id  cmd  age`
  - Scrollable when right panel is focused

---

## Section 3: Scope & Constraints

### Files Changed
| File | Change |
|------|--------|
| `dashboard.py` | `_draw_hero()` vitals footer; `_draw_overview()` restructure; `_section_header()` helper; nav contrast |

### Files Unchanged
| File | Reason |
|------|--------|
| `cards.py` | Data source only — status column reads card data directly |
| `skins.py` | Existing color pairs cover all new elements |
| `soil.py` | No schema changes |
| `skins.py` | No new skin properties needed |

### Out of Scope
- Mission control treatment for pages 2–9 (Kart, Yggdrasil, etc.) — follow-on
- Color palette changes — current blue/green/amber is correct for mission control
- Skin system extensions
- New key bindings

### Success Criteria
- Open the dashboard → reads like a live ops room within 2 seconds
- Status column conveys system health without expanding or navigating anywhere
- Chat feels like issuing commands to an ops system
- No regressions on other pages
