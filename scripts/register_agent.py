#!/usr/bin/env python3
"""
register_agent.py — Register a new agent with the Willow dashboard
b17: RAGT1  ΔΣ=42

Usage:
    python3 scripts/register_agent.py

Writes to ~/.willow/agents.json (local override, picked up by dashboard).
Prints a PR-ready snippet to add to willow-1.7/sap/sap_mcp.py for full system registration.
"""
import json
import sys
from pathlib import Path

TRUST_LEVELS = {
    "1": ("WORKER",   "Professor / faculty member — SAFE-signed app"),
    "2": ("ENGINEER", "Infrastructure agent — Claude Code CLI or system worker"),
    "3": ("OPERATOR", "Operator tier — primary interface or coordinator"),
}

AGENTS_FILE = Path.home() / ".willow" / "agents.json"


def load_existing():
    if AGENTS_FILE.exists():
        try:
            return json.loads(AGENTS_FILE.read_text())
        except Exception:
            pass
    return []


def save(agents):
    AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENTS_FILE.write_text(json.dumps(agents, indent=2))


def main():
    print("── Willow Agent Registration ──")
    print()

    existing = load_existing()
    existing_names = {a["name"] for a in existing}

    name = input("Agent name (lowercase, no spaces): ").strip().lower()
    if not name or not name.isidentifier():
        print("Invalid name.")
        sys.exit(1)
    if name in existing_names:
        print(f"Agent '{name}' already registered locally.")
        sys.exit(0)

    role = input("Role description (one sentence): ").strip()
    if not role:
        print("Role required.")
        sys.exit(1)

    print()
    print("Trust level:")
    for k, (trust, desc) in TRUST_LEVELS.items():
        print(f"  {k}. {trust} — {desc}")
    trust_choice = input("Choose [1/2/3] (default 1): ").strip() or "1"
    trust, _ = TRUST_LEVELS.get(trust_choice, TRUST_LEVELS["1"])

    entry = {"name": name, "trust": trust, "role": role}

    # Write to local override file
    existing.append(entry)
    save(existing)
    print()
    print(f"✓ Registered locally: ~/.willow/agents.json")
    print(f"  {entry}")

    # Print PR snippet for willow-1.7
    print()
    print("── To register system-wide, add this line to willow-1.7/sap/sap_mcp.py ──")
    print(f'  Line ~850 in the willow_agents handler:')
    print()
    print(f'    {{"name": "{name}", "trust": "{trust}", "role": "{role}"}},')
    print()
    print("Then open a PR to https://github.com/rudi193-cmd/willow-1.7")
    print()
    print("── To run the dashboard as this agent ──")
    print(f"  WILLOW_AGENT_NAME={name} python3 dashboard.py")


if __name__ == "__main__":
    main()
