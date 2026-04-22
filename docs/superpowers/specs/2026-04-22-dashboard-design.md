# Dashboard Design Spec — The Orchestration Terminal

**Spec path:** `willow-dashboard/docs/superpowers/specs/2026-04-22-dashboard-design.md`

**Authors:** Design Claude (claude.ai), with Hanuman (willow-1.9 orchestrator + safe-app-grove) and Heimdallr (willow-dashboard).
**Date:** 2026-04-22
**Status:** Draft 1 — ready for Heimdallr implementation.
**Constraint:** stdlib curses only. No textual, no rich, no blessed. Per `willow-dashboard/CLAUDE.md`.

---

## 1. What this is

This spec describes the dashboard's **new identity**: the human control surface for a sovereign, multi-model AI orchestration layer.

It is no longer a monitoring tool.

It shows — at a glance, without navigation — what the system is doing right now, across every agent, every model, every Grove channel, every running session. It also provides the on-demand depth the older card system gave us. Both layers matter. This spec specifies the *always-visible* layer in detail, because that's the layer that changed. The on-demand card grid stays as it is today.

## 2. Why it changed

Grove (`#architecture` id 16) reframed the product:

> "We are building OpenClaw but we are building Willow."

OpenClaw (single-model vendor framework) is not what this is. Willow is a sovereign, local-first, multi-model orchestration platform. Multiple projects, multiple agents, multiple models, one coordination fabric (Grove) and one memory layer (Willow-KB).

The dashboard is the terminal that makes the whole thing legible. That is a different product than "a TUI that shows system vitals." It needs to show who is running where, where intents are being routed, what's happening on Grove, and what the knowledge base is doing — all in one pane, all at once.

## 3. Design principles

1. **Terminal-native, unapologetic.** The reference is tmux, k9s, htop, lazygit, ranger — dense, keyboard-driven, colored text, no chrome. People who will run Willow already live in this idiom.
2. **Always-visible over on-demand.** The moment the dashboard becomes "I have to tab to that to see it," that thing is not in the critical set.
3. **Destroyed-first, preserved-second.** Any destructive action renders the reactor-door placard. Not a modal confirm. See §8.
4. **Color carries meaning.** Sender-by-hash for Grove; status-by-state for agents and vitals; single accent (bright yellow) for things that need attention right now.
5. **The strip is a contract.** Its shape and column order are stable. Agents, scripts, and external readers depend on the ordering. Changes are breaking changes.

## 4. The six regions

```
┌─── willow • sean-campbell ─────────────────────── 13:04:22 ─┐
│ VITALS   pg ●  ollama ●  kart 3/12  soil ●  ledger ok       │
├─────────────────────────────────────────────────────────────┤
│ AGENTS   hanuman (willow-1.9)     • running  12m            │
│          hanuman (safe-app-grove) • running  34m            │
│          heimdallr (dashboard)    • running   6m            │
│          oakenscroll (claude.ai)  • idle     ——             │
├─────────────────────────────────────────────────────────────┤
│ ROUTING  13:04 "debug gleipnir rate limit"      → ganesha   │
│          13:01 "search prior session on routes" → jeles     │
│          12:58 "post update to architecture"    → grove     │
│          12:55 "what did I ship yesterday"      → willow    │
├─────────────────────────────────────────────────────────────┤
│ GROVE    #general       ·                                    │
│          #architecture  • 2                                  │
│          #handoffs      ·                                    │
│          #readme        ·                                    │
├─────────────────────────────────────────────────────────────┤
│                     [ card workspace ]                       │
├─────────────────────────────────────────────────────────────┤
│ q quit  ? help  r refresh  / search  n nuke                  │
└─────────────────────────────────────────────────────────────┘
```

### Region 1 — VITALS strip

Extends the existing vitals line. Same row, same position. Order is fixed: `pg · ollama · kart · soil · ledger`. Each is a single indicator glyph — `●` green / yellow / red / `○` gray (unknown). `kart` shows `running/queued` as a compact fraction. State change redraws the cell; no animation.

### Region 2 — AGENTS

Rolling list of every known agent session. Row format:

```
  <agent-name> (<project/session>)     <state>   <uptime>
```

States: `running` (heartbeat <2m) · `idle` (2–15m) · `stale` (15m–1h, dimmed) · `gone` (>1h, removed next tick).

Color by hash of agent name — same palette as Grove TUI (`cyan, magenta, yellow, bright_green, bright_blue, bright_red, bright_cyan`), so `hanuman` is always the same color everywhere on this machine. Load-bearing principle: **one person, one color, across every surface**. That's how the eye catches multi-session coordination at a glance.

Heartbeat source: `grove.messages.created_at` aggregated by `sender`, plus `willow.sap_sessions.last_seen_at` joined on session token when available.

### Region 3 — ROUTING

Live decision feed from `willow_route`. Row format:

```
  HH:MM  "<prompt snippet, ≤40 chars>"   → <agent>
```

- Most recent first, last 8 rows.
- Prompt truncated to 40 chars with ellipsis.
- Target agent colored via same hash palette as region 2.
- Rule source shown only in the routing card (region 5), not the strip.
- Region renders even when empty: `no routing decisions yet this session`.

Data shape — final, reconciled:

```json
{
  "ts": "2026-04-22T13:04:12Z",
  "prompt_snippet": "debug gleipnir rate limit",
  "routed_to": "ganesha",
  "rule_matched": "rule-ganesha-debug",
  "confidence": 0.92,
  "latency_ms": 3
}
```

- `rule_matched` never null — literal `"llm-fallback"` when Yggdrasil decides.
- `confidence`: 1.0 for deterministic matches, LLM self-report otherwise. Dashboard may dim rows <0.7.
- Storage: `willow.routing_decisions` Postgres table, retention last 1000.
- Dashboard reads `ORDER BY ts DESC LIMIT 8` on 1s poll.

### Region 4 — GROVE

Channel list with unread indicator. Row format:

```
  #<channel-name>   <unread-glyph> [<count>]
```

- `·` (middle dot, dim) — no unread.
- `•` (bullet, bright yellow) — unread present, count follows.

Reads `grove.messages` joined against per-dashboard `last_seen_id` stored in SOIL (`willow/dashboard/channel_cursors`). Opening a channel card advances the cursor.

Channel order stable: `general, architecture, handoffs, readme, <others alpha>`. Muscle memory matters.

### Region 5 — CARD WORKSPACE

Existing card system, unchanged by this spec. New cards implied (internal spec out of scope):

- **Routing card** — full decision history, rule source, latency, LLM fallback reasoning when applicable.
- **Channel card** (per Grove channel) — full message view, colored senders, input bar. Grove TUI embedded.
- **Agent card** (per session) — session log, recent Willow tool calls, cwd, last prompt.

### Region 6 — KEY STRIP

Existing footer pattern. Adds `n nuke` — not a modal, a full-screen takeover (§8).

## 5. Color and glyphs

ANSI 16 only. No 256-color, no RGB.

| Use | Color |
|---|---|
| Healthy | `green` |
| Degraded | `yellow` |
| Down / error | `red` |
| Unknown | `default` + `dim` |
| Timestamps | `dim` |
| Active focus | `bold` |
| Nuke placard | `red` on `default` |
| Sender/agent hash | `cyan, magenta, yellow, bright_green, bright_blue, bright_red, bright_cyan` |

Glyphs: Unicode BMP only. `●`, `○`, `·`, `•`, `→`, `←`, `↑`, `↓`. No emoji. Single exception: `🍊` when Sean explicitly types it (CMB atom surfacing).

## 6. Keyboard

| Key | Action |
|---|---|
| `q` | Quit (dirty-state check) |
| `?` | Help overlay |
| `r` | Force refresh (auto-ticks 1s) |
| `/` | Global search (Willow + Grove) |
| `1`–`9` | Jump to region / card by ordinal |
| `j / k` | Move selection |
| `g / G` | Top / bottom |
| `Enter` | Open focused item as card |
| `Esc` | Close card, return to strip |
| `n` | Nuke — reactor-door placard |

`n` is deliberately at the end of the strip. Ordinary workflow doesn't put fingers near it.

## 7. Data access

Same Postgres database the dashboard already reads for Kart. New tables/schemas this spec reads from:

- `grove.messages` — regions 4 and 5 (channel card)
- `grove.channels` — region 4
- `willow.sap_sessions` — region 2 agent heartbeats (fall back to aggregating `grove.messages.sender` when sap session is unavailable)
- `willow.routing_decisions` — region 3. `willow_route` is the writer.

No new MCP calls required — direct SQL read, same pattern as the existing kart card.

Poll cadence: 1s. All four read-regions fit in a single transaction (one `SELECT` per region, five total including vitals). If query time exceeds 200ms at any poll, log and degrade gracefully — the strip shows a dimmed `(slow)` indicator next to `pg` in the vitals line.

**Open dependency:** `willow.sap_sessions.last_seen_at` — assumed to exist or be addable. Fallback: aggregate `grove.messages.sender` + `created_at` only.

## 8. The reactor-door placard

When `n` is pressed — or any code path invokes the nuke flow — the dashboard takes over the terminal with a double-ruled ASCII placard. Not a modal.

```
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║                        ▲  IRREVERSIBLE ACTION  ▲                      ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  WHAT WILL BE DESTROYED                                               ║
║  ───────────────────────                                              ║
║    • All atoms in ~/.willow/store/                                    ║
║    • All sessions in willow.sap_sessions                              ║
║    • All LOAM atoms in willow_19                                      ║
║    • FRANK's ledger chain from genesis                                ║
║    • Grove messages in this database                                  ║
║                                                                       ║
║  WHAT WILL BE PRESERVED                                               ║
║  ──────────────────────                                               ║
║    • Your SSH keys                                                    ║
║    • Your GPG keys                                                    ║
║    • Your Postgres cluster (only the willow_19 database is dropped)   ║
║    • Files outside ~/.willow/                                         ║
║                                                                       ║
║  There is no undo. There is no recovery. There is no backup this      ║
║  script is quietly keeping for you.                                   ║
║                                                                       ║
║  To proceed, type:   I UNDERSTAND                                     ║
║  To abort, press:    Esc                                              ║
║                                                                       ║
║                                                                       ║
║  > _                                                                  ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
```

**Rules:**

- Destroyed list is **always first**, preserved list **always second**. The grammar: tell the operator what they are losing before you tell them what they are keeping.
- No FRANK voice here. No jokes. No emoji. Plain terminal speech. This is the one surface where the system is *not* performing anything.
- Confirm phrase is `I UNDERSTAND`. Not `YES`. Not the database name. The exact phrase because the act of typing it **is** the consent.
- Same placard renders at install time in `boot.py` when the operator selects "reinitialize" or runs `willow nuke` directly. **Same ASCII, same wording, same rules.** Dashboard for runtime destruction, boot.py for install-time destruction. Two moments, one grammar.

## 9. What this spec does NOT cover

- Per-card internal design (routing / channel / agent card interiors).
- `willow_route` algorithm (rule + Yggdrasil hybrid) — covered in `#architecture` id 18; this spec consumes its output only.
- `boot.py` onboarding layer (the new "what is Willow / what you own / psr_names" preamble) — Oakenscroll drafting.
- Scriptable dashboard actions (cron-like triggers, batch ops). Not in v1.

## 10. Acceptance checklist

- [ ] Regions 1–4 render simultaneously within 1s of startup.
- [ ] All regions redraw within 100ms of a data change on a 1s poll.
- [ ] Agent colors stable across process restarts (hash input: `agent-name`, not session id).
- [ ] Region 4 unread counts advance correctly when a channel card opens.
- [ ] Pressing `n` at any time renders the placard; no modal or dialog library used.
- [ ] Typing `I UNDERSTAND` exactly (case-sensitive, single space) triggers nuke; anything else is inert.
- [ ] Esc from placard returns to previous dashboard state with no side effects.
- [ ] All colors are ANSI 16 or `default`. No 256-color.
- [ ] No dependencies beyond stdlib.
- [ ] Terminal min 80×24. Below that: single message *"terminal too small — resize to 80×24 or larger"*, clean exit on `q`.

## 11. Open questions for Sean

1. **Routing feed prompt snippet redaction:** prompts can contain PSR names, credentials, ledger keys. Redact in region 3 when intent is flagged sensitive? Default: no — Sean is the only operator. Revisit if ever multi-user on one machine.

2. **Agent color stability:** palette is 7 colors; >7 agents means collisions. Acceptable (each agent's color still stable, muscle memory works), or extend to deterministic 16-color?

3. **Card full-screen behavior:** when a card is open, do regions 1–4 stay sticky above it, or does the card take the full pane? Default proposal: strip stays, cards take region 5 only.

---

ΔΣ=42

*Authored by Design Claude (claude.ai). Coordinated with Hanuman (willow-1.9 + safe-app-grove) and Heimdallr (willow-dashboard) via Grove `#architecture` channel, 2026-04-22.*
