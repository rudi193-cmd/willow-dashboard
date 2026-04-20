# Willow Dashboard — Operating Rules
b17: WDASH  ΔΣ=42

## Who I Am

I am the Claude Code instance working on `willow-dashboard` — the Willow system terminal TUI. This repo was spun out of `willow-1.7/apps/` on 2026-04-19.

**The dashboard is agent-neutral.** The agent running it is set at launch via `WILLOW_AGENT_NAME`. Default is `heimdallr` but any registered Willow agent can run it — Oakenscroll, Gerald, Shiva, Nova, or a new one. The chat persona, header display, and `app_id` all derive from that env var.

---

## What This Is

A pure-Python curses terminal dashboard for the Willow system. No web, no HTTP, no extra framework. Runs with `python3 dashboard.py`.

**Current state (as of first commit `aeb5071`):**
- Animated willow tree hero block (3-pose sway, 10-frame loop, spring scene)
- 9-page navigation: Overview, Kart, Yggdrasil, Knowledge, Secrets, Agents, Logs, Settings, Help
- Panel-aware navigation: Tab cycles focus None→left→right, yellow border on active panel
- Interactive Heimdallr chat in Overview left panel — Ollama streaming + fleet fallback
- Live system cards: Postgres stats, Ollama models, SAFE manifests, Kart queue
- Keys: Tab=focus, ←→=pages (unfocused), ↑↓=navigate, Enter=expand, Esc=back, 1-9=jump, r=refresh, q=quit

---

## Willow System Context

This dashboard talks to the Willow system running on the same machine:

| Component | What it is | How dashboard connects |
|-----------|-----------|------------------------|
| SAP | Portless MCP auth gate, 49 tools, PGP-hardened | Not directly — dashboard calls underlying layers |
| LOAM | Postgres KB: 68K atoms, 1M edges, unix socket peer auth | `psycopg2` via `WILLOW_DB_URL` env var |
| SOIL | SQLite local store: 78 collections, 2M+ records | Via `willow-1.7/core/willow_store.py` |
| Ollama | Local inference: yggdrasil:v8/v9, qwen2.5:3b, etc. | `http://localhost:11434` via urllib |
| SAFE | PGP-signed manifests for every professor app | `WILLOW_SAFE_ROOT` env var → `~/SAFE_backup/Applications` |
| Kart | Task queue worker | Postgres `kart.kart_task_queue` table |
| Yggdrasil | Local SLM trained on Willow operational patterns | Ollama model `yggdrasil:vN` |
| Credentials | Fernet-encrypted SQLite vault + `~/.willow/secrets/credentials.json` | `_get_vault_key()` in dashboard.py |

**Fleet providers (keys in credentials.json):**
- `GROQ_API_KEY` → Groq llama-3.3-70b-versatile
- `CEREBRAS_API_KEY` → Cerebras llama3.1-8b
- `SAMBANOVA_API_KEY` → SambaNova Meta-Llama-3.3-70B
- Note: all fleet keys returned 403 on 2026-04-19 — may need refreshing

---

## Heimdallr Chat

The Overview page left panel is a live chat. Routing:
1. Try Ollama streaming (`yggdrasil:vN`) — confirmed working, knows Willow
2. Fall back to fleet via `_get_vault_key()` → credentials.json

System prompt in `HEIMDALLR_SYSTEM` — terse, names components, no padding.

**Confirmed working:** yggdrasil:v8 via Ollama responded correctly to Willow questions.

---

## What's Next

The dashboard was freshly graduated from willow-1.7. Obvious next steps:
- Wire Knowledge page search to `willow_knowledge_search` MCP tool
- Wire Kart page to live Postgres task data
- Refresh fleet API keys (all 403)
- Session persistence for chat history
- Journal pipeline integration (log chat exchanges)
- Settings page — make config actually editable

---

## Rules

1. **No web, no HTTP server, no ports.** This is a terminal app. Portless means portless.
2. **stdlib curses only** — no textual, no rich, no blessed. Sean chose no extra dependencies.
3. **MCP is the bus** for any KB reads/writes — use `willow_knowledge_search`, `store_put`, etc.
4. **b17 on every new file before it is closed.**
5. **Propose before acting.** Sean ratifies. Neither party acts alone.

---

ΔΣ=42
