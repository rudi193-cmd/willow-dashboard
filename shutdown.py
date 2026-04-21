"""shutdown.py — Graceful shutdown orchestrator for Willow Dashboard.
b17: WDASH  ΔΣ=42

Reads ~/.claude/commands/shutdown.md and runs the /shutdown sequence
through the active agent (Heimdallr or configured model) in the chat panel.

The right panel shows friendly progress during shutdown.
Developer mode (toggled in Settings) shows raw agent output.
"""
from dataclasses import dataclass, field
from pathlib import Path
import threading

# ── Shutdown skill location ───────────────────────────────────────────────────
SHUTDOWN_SKILL_PATH = Path.home() / ".claude" / "commands" / "shutdown.md"

# ── Step definitions — internal name + user-facing description ────────────────
STEPS: list[tuple[int, str, str]] = [
    (1,  "Reviewing what was learned this session",   "atom_audit"),
    (2,  "Archiving outdated information",            "archive_stale"),
    (3,  "Updating records that changed",             "correct_drift"),
    (4,  "Checking for open questions and gaps",      "gaps_audit"),
    (5,  "Saving new knowledge",                      "write_new_atoms"),
    (6,  "Connecting related ideas",                  "edge_consent_gate"),
    (7,  "Writing session summary",                   "handoff"),
    (8,  "Compiling today's log",                     "write_daily_log"),
    (9,  "Scanning for unsaved code",                 "prompt_unpushed"),
    (10, "Cleaning up",                               "close_session"),
]

# Step 6 is interactive — requires user input in the chat panel
INTERACTIVE_STEPS = {6}

# Completion marker the agent embeds in its output (stripped from friendly view)
STEP_MARKER = "[SHUTDOWN:STEP:{n}:COMPLETE]"
SHUTDOWN_COMPLETE_MARKER = "[SHUTDOWN:COMPLETE]"


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class ShutdownState:
    active:         bool  = False
    complete:       bool  = False
    current_step:   int   = 0          # 0 = not started, 1-10 = in progress
    step_status:    dict  = field(default_factory=dict)   # {n: "pending"|"running"|"done"|"error"}
    raw_mode:       bool  = False      # toggled via Settings
    waiting_input:  bool  = False      # True during interactive steps
    input_prompt:   str   = ""         # friendly prompt shown to user
    aborted:        bool  = False

    def status_for(self, n: int) -> str:
        return self.step_status.get(n, "pending")

    def mark_running(self, n: int):
        self.current_step = n
        self.step_status[n] = "running"

    def mark_done(self, n: int):
        self.step_status[n] = "done"

    def mark_error(self, n: int):
        self.step_status[n] = "error"


SHUTDOWN = ShutdownState()

# ── Icons ─────────────────────────────────────────────────────────────────────
STEP_ICONS = {
    "pending": "○",
    "running": "⟳",
    "done":    "✓",
    "error":   "✗",
}


# ── Skill loader ──────────────────────────────────────────────────────────────

def load_shutdown_skill() -> str:
    """Read the /shutdown skill definition."""
    if SHUTDOWN_SKILL_PATH.exists():
        return SHUTDOWN_SKILL_PATH.read_text()
    return ""


def build_shutdown_prompt() -> str:
    """Build the system prompt injection for the shutdown sequence."""
    skill = load_shutdown_skill()
    marker_instructions = "\n\n".join([
        f"After completing step {n} ({name}), output exactly: "
        f"{STEP_MARKER.format(n=n)}"
        for n, _, name in STEPS
    ])
    return f"""You are now running the /shutdown sequence for the Willow Dashboard.

{skill}

IMPORTANT OUTPUT INSTRUCTIONS:
After completing each step, emit the exact completion marker on its own line.
{marker_instructions}

When the entire sequence is complete, output: {SHUTDOWN_COMPLETE_MARKER}

These markers are used by the dashboard to track progress. Do not omit them.
"""


# ── Message parser ────────────────────────────────────────────────────────────

def parse_agent_message(text: str) -> tuple[list[int], bool, str]:
    """Parse an agent message for step completion markers.

    Returns:
        completed_steps: list of step numbers completed in this message
        shutdown_complete: whether the full shutdown is done
        clean_text: message with markers stripped (for friendly display)
    """
    completed = []
    shutdown_complete = False
    clean = text

    for n, _, _ in STEPS:
        marker = STEP_MARKER.format(n=n)
        if marker in clean:
            completed.append(n)
            clean = clean.replace(marker, "").strip()

    if SHUTDOWN_COMPLETE_MARKER in clean:
        shutdown_complete = True
        clean = clean.replace(SHUTDOWN_COMPLETE_MARKER, "").strip()

    return completed, shutdown_complete, clean


def friendly_text(raw: str) -> str:
    """Strip technical content for casual users.

    Removes: SQL queries, JSON blobs, store IDs, error tracebacks.
    Keeps: plain sentences, agent commentary, questions for the user.
    """
    lines = []
    skip_patterns = (
        "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
        "store_", "willow_", "{", "```",
        "Traceback", "Error:", "Exception:",
        "[SHUTDOWN:", "b17:",
    )
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if any(stripped.upper().startswith(p.upper()) or p in stripped
               for p in skip_patterns):
            continue
        lines.append(line)

    # Collapse multiple blank lines
    result = []
    prev_blank = False
    for l in lines:
        if l.strip() == "":
            if not prev_blank:
                result.append(l)
            prev_blank = True
        else:
            result.append(l)
            prev_blank = False

    return "\n".join(result).strip()


# ── Trigger ───────────────────────────────────────────────────────────────────

def initiate_shutdown(send_chat_fn) -> None:
    """Start the shutdown sequence. send_chat_fn is dashboard.send_chat."""
    global SHUTDOWN
    SHUTDOWN = ShutdownState(active=True)

    # Mark all steps pending
    for n, _, _ in STEPS:
        SHUTDOWN.step_status[n] = "pending"

    prompt = build_shutdown_prompt()

    def _run():
        SHUTDOWN.mark_running(1)
        send_chat_fn("[SYSTEM] Begin /shutdown sequence.", system_override=prompt)

    threading.Thread(target=_run, daemon=True).start()


def process_agent_message(raw_text: str) -> str:
    """Call this when a new agent message arrives during shutdown.

    Updates ShutdownState and returns the text to show (friendly or raw).
    """
    completed, done, clean = parse_agent_message(raw_text)

    for n in completed:
        SHUTDOWN.mark_done(n)
        # Start next step if there is one
        next_steps = [s for s, _, _ in STEPS if s > n]
        if next_steps:
            SHUTDOWN.mark_running(next_steps[0])

    if done:
        SHUTDOWN.complete = True

    # Friendly mode: strip technical output
    display = clean if SHUTDOWN.raw_mode else friendly_text(clean)
    return display


def is_complete() -> bool:
    return SHUTDOWN.complete


def description_for_step(n: int) -> str:
    for num, desc, _ in STEPS:
        if num == n:
            return desc
    return ""
