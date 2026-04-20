# Card System Design
b17: WDASH  ΔΣ=42
date: 2026-04-20
status: approved

---

## Overview

A generic, user-configurable card system for the Willow Dashboard. Users elect which cards appear on the Overview grid. Cards expand to fill the right panel as mini-pages with live data and action keys. New cards are created conversationally through the Heimdallr chat — the agent interviews the user, generates a SOIL collection schema and card definition, and writes both without any code required.

---

## 1. Architecture

**Two rendering paths — hybrid model:**

**Built-in cards** ship with the dashboard and have custom Python renderer functions (`draw_kart_right()`, `draw_knowledge_right()`, etc.). They are always enabled and can be reordered but not hidden or deleted.

**Dynamic cards** are user-created or imported. A single `draw_dynamic_card(card_def)` renderer reads a card definition from SOIL and handles both grid and expanded view generically.

Both types are records in the `willow-dashboard/cards` SOIL collection. On startup the dashboard seeds built-in card definitions if absent. The grid renders all enabled cards in `order` sequence.

**Expand behavior:**
- Tab → focus right panel → arrow keys select a card → Enter expands it
- Expanded card fills the entire right panel
- Expanded view: card title + data list + action key hints at bottom
- Esc collapses back to grid
- The Hero Bar (left panel: willow animation, agent name, chat) is untouched throughout all states

**Grid scroll:**
- When enabled cards exceed visible grid rows, the grid scrolls vertically
- Selection drives scroll — selected card always stays in view
- Scroll position indicator shown at grid bottom (e.g. `4-10 / 14`)

---

## 2. Card Definition Schema

Every card is a record in SOIL collection `willow-dashboard/cards`.

```
id               string   unique slug — "kart", "job-hunt", "projects"
label            string   display name shown on grid card
category         string   system | work | dev | personal
built_in         bool     true = ships with dashboard, always enabled
enabled          bool     false = in catalog but not on grid (user cards only)
order            int      position in grid; built-ins seed at 0-6, user cards append

# Grid display (all queries are SQLite against SOIL or Postgres via pg_table)
value_query      string   returns single value — shown large on card
sub_query        string   returns single value — shown as subtitle (optional)
sub_format       string   "{} interviews" — {} replaced by sub_query result
state_query      string   returns "green" | "amber" | "red" | "blue" — card color

# Data source — exactly one of:
soil_collection  string   SQLite collection name e.g. "job-hunt/applications"
pg_table         string   Postgres table name e.g. "kart_task_queue"

# Expanded view
expand_query     string   returns rows displayed when card is expanded
expand_columns   list     field names to display and their order

# Actions (shown as key hints when expanded)
actions          list     list of action objects:
                            key    string  single keystroke e.g. "a"
                            label  string  e.g. "add application"
                            type   string  form | confirm | chat
                          "chat" hands off to Heimdallr in the left panel

# Housekeeping
refresh_interval int      seconds between data refreshes, default 60
skin_override    object   null — reserved for per-card skin overrides (not implemented)
```

---

## 3. Skin System

Skins live in SOIL collection `willow-dashboard/skins`. The active skin ID is stored in `willow-dashboard/config` under key `active_skin`. Default is `"default"`.

```
id               string   skin slug
label            string   display name

# Colors — terminal color indices (0-255, or -1 for terminal default)
color_header     int      page titles, section headers
color_value      int      large value on card (default: blue)
color_green      int      status good
color_amber      int      status warn
color_red        int      status bad / error
color_dim        int      secondary / muted text
color_pill       int      stat strip pills
color_select     int      selected card highlight
color_border     int      panel borders
color_hero       int      willow tree color in Hero Bar

# Layout
grid_columns     int      1 | 2 | 3 — card grid columns, default 2
left_width_pct   int      left panel as % of terminal width, default 66
border_style     string   "box" | "minimal" | "none"
card_height      int      rows per card in grid, default 4
stat_strip       bool     show/hide bottom stat strip

# Extension point
custom           object   null — reserved for future full renderer overrides
```

**Five skins that ship with the dashboard:**

| ID | Name | Character |
|----|------|-----------|
| `default` | Default | Blue/green/amber on dark. Ships today. |
| `midnight` | Midnight | Near-black background, violet accent. |
| `forest` | Forest | Deep green, earthy amber. Fits the willow. |
| `amber` | Amber | Classic phosphor terminal. Warm, easy on eyes. |
| `accessible` | High Contrast | Pure black/white base, yellow/orange accents. **Status conveyed by symbol AND color** (✓ ▲ ✗ ●) — works for deuteranopia, protanopia, monochrome displays, and low vision. Symbol key shown at grid bottom. |

The `accessible` skin is the only one that changes rendering behavior — it prefixes card values with status symbols so color is never the sole signal. Both built-in card renderers and `draw_dynamic_card()` must check the active skin's `accessible` flag and prepend the appropriate symbol (✓ ▲ ✗ ●) based on the card's state value. The symbol key (`✓=ok  ▲=warn  ✗=err  ●=info`) is rendered at the bottom of the grid when this skin is active.

---

## 4. Heimdallr Card Creation Flow

**Trigger points (both active):**
1. Natural language in the Overview chat — any message containing "add card", "create card", "track my X", etc.
2. Enter on the `+` card in the Overview grid — immediately prompts in chat

**New project flow:**
1. Heimdallr asks: new project or import existing?
2. If new: interview — what to track, what fields, what status values exist
3. Confirms what the grid card will show at a glance
4. Asks what actions should be available when expanded
5. Writes SOIL collection schema to `<category>/<name>`
6. Writes card definition to `willow-dashboard/cards`
7. Confirms to user: "Press r to see it on the grid"

**Import existing flow:**
1. Heimdallr asks: new project or import existing?
2. If import: user names the SOIL collection or Postgres table
3. Heimdallr reads its schema and reports fields + record count
4. Same questions: what to show at a glance, what actions
5. Writes card definition only — no schema changes to existing data
6. Confirms to user

**Heimdallr generates all SQL queries.** The user never writes a query. Queries are validated by running them once before the card definition is written; errors surface in chat.

**How the dashboard writes SOIL records from chat:** Heimdallr is prompted with a card-creation system prompt that instructs it to emit a fenced ````card-def` JSON block when the interview is complete. The dashboard's chat loop detects this block, parses it, validates the queries, and writes the SOIL records. The user sees a confirmation message. Heimdallr never calls SOIL directly — the dashboard owns all writes.

---

## 5. Card Catalog

### Built-in cards (always on, reorderable, never hidden)

| ID | Label | Data source | Expanded actions |
|----|-------|-------------|-----------------|
| `kart` | Kart Queue | Postgres `kart_task_queue` | c=cancel, r=retry |
| `knowledge` | Knowledge | Postgres `public.knowledge` | /=search (chat) |
| `yggdrasil` | Yggdrasil | Ollama API | pull new version (chat) |
| `agents` | Agents | SAFE manifests + `willow_agents` | view per-agent detail |
| `secrets` | Secrets Vault | `~/.willow_creds.db` | reveal (confirm) |
| `fleet` | Fleet | Credentials + live ping | ping, update key (chat) |
| `mcp` | MCP Servers | `.mcp.json` files | list tools, show auth state |

### Optional catalog cards (user-elected, seeded as disabled)

**Work / Projects**
- `projects` — Projects: active count, overdue. Actions: add, update, archive.
- `job-hunt` — Job Hunt: applications in flight, interviews scheduled. Actions: add, update status.
- `notes` — Notes: recent note count. Actions: quick-add inline.
- `journal` — Journal: today's entry status. Actions: append a line.
- `goals` — Goals: active goals + completion %. Actions: check off items.

**Code / Dev**
- `git-status` — Git Status: current repo, branch, dirty/clean. Actions: view log.
- `open-prs` — Open PRs: awaiting review count. Actions: view list.
- `build` — Build / CI: last build status. Actions: view log.
- `todos` — TODOs: open count in codebase. Actions: view file:line list.

**Personal / Life**
- `calendar` — Calendar: next event. Actions: view today's schedule.
- `habits` — Habits: daily streak counts. Actions: check off today.
- `reading` — Reading List: currently reading + queue depth. Actions: mark finished, add.

---

## 6. What Doesn't Change

- The Hero Bar (willow animation, LIVE indicator, agent name, Heimdallr chat) is fixed. Skins may change the tree color but not the layout or presence of the Hero Bar.
- The page navigation (1-9 keys, page tab bar) is unchanged.
- Existing pages (Kart, Knowledge, Yggdrasil, etc.) remain as full pages — the Overview cards are summaries that link into them.

---

## Out of Scope (this spec)

- Full custom skin renderer overrides (`skin.custom`) — stub only
- Card-to-card relationships or dependencies
- Card sharing between Willow users
- Card versioning or history
