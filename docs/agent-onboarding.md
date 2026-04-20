# Agent Onboarding
<!-- b17: AGOB1 · ΔΣ=42 -->

This is the onboarding pipeline for new agents joining the Willow system via the dashboard.

## What happens when you register

```
scripts/register_agent.py
        │
        ▼
~/.willow/agents.json          ← local override file
        │
        ├── dashboard.py reads it on startup
        │       └── agent appears in Settings page
        │       └── WILLOW_AGENT_NAME=yourname works immediately
        │
        └── sap_mcp.py merges it at runtime
                └── willow_agents MCP tool returns your agent
                └── you're visible system-wide
```

No PR required for local use. No edits to core files.

## Quickstart

```bash
git clone https://github.com/rudi193-cmd/willow-dashboard
cd willow-dashboard
python3 scripts/register_agent.py
```

Follow the prompts:
- **Name** — lowercase, no spaces (e.g. `nova`, `riggs`, `yourname`)
- **Role** — one sentence describing what you do
- **Trust level** — WORKER (default), ENGINEER, or OPERATOR

Then run the dashboard as your agent:

```bash
WILLOW_AGENT_NAME=yourname python3 dashboard.py
```

## Trust levels

| Level | Who | What it means |
|-------|-----|---------------|
| WORKER | Professors, faculty | SAFE-signed app, standard access |
| ENGINEER | Claude Code CLI, infra workers | Infrastructure access, task queue |
| OPERATOR | Primary interfaces, coordinators | Top-level system access |

Default for new registrations: **WORKER**.

## Going system-wide

Local registration writes to `~/.willow/agents.json` — visible on your machine only.

To register system-wide (visible to all nodes), add the snippet printed by the script to `willow-1.7/sap/sap_mcp.py` and open a PR:

```
https://github.com/rudi193-cmd/willow-1.7
```

The script prints the exact line to add.

## The pattern

> A new agent joins Willow the same way a professor joins a faculty — they register, they get a role, and they become visible to the system. The friction is near zero for local use. The PR path exists for permanence.

---
ΔΣ=42
