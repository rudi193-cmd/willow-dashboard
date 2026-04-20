# willow-dashboard
<!-- b17: WDASH · ΔΣ=42 -->

Heimdallr — terminal dashboard for the [Willow system](https://github.com/rudi193-cmd/willow-1.7).

Pure Python, no extra dependencies beyond stdlib. Optional: `cryptography` (vault key access), `psycopg2` (live Postgres stats).

## Run

```bash
python3 dashboard.py

# Run as a specific agent
WILLOW_AGENT_NAME=oakenscroll python3 dashboard.py
WILLOW_AGENT_NAME=gerald python3 dashboard.py
WILLOW_AGENT_NAME=shiva python3 dashboard.py
```

## Keys

| Key | Action |
|-----|--------|
| `Tab` | Cycle focus: none → left → right |
| `← →` | Switch pages (when no panel focused) |
| `↑ ↓` | Scroll log / navigate list |
| `1–9` | Jump to page |
| `Enter` | Expand selected item |
| `Esc` | Collapse / unfocus |
| `r` | Force data refresh |
| `q` | Quit |

## Pages

1. **Overview** — Heimdallr chat + system card grid
2. **Kart** — task queue
3. **Yggdrasil** — local SLM models
4. **Knowledge** — KB search
5. **Secrets** — credential vault
6. **Agents** — SAFE manifests
7. **Logs** — activity log
8. **Settings** — configuration
9. **Help** — keyboard reference

## Chat

The Overview left panel is a live chat with Heimdallr. Routes to:
1. Local Ollama (yggdrasil model) — streaming
2. Fleet fallback — reads `GROQ_API_KEY` / `CEREBRAS_API_KEY` / `SAMBANOVA_API_KEY` from `~/.willow/secrets/credentials.json` or the Fernet vault at `~/.willow_creds.db`

## Architecture

Connects to the Willow SAP server (`willow-1.7`) for live data:
- Postgres (LOAM) — KB atoms, edges, Kart queue
- Ollama — local Yggdrasil SLM
- SAFE root — manifest verification

---
ΔΣ=42
