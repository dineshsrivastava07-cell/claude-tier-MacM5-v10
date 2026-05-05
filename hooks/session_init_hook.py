#!/usr/bin/env python3
"""
DSR AI-Lab · Session Init Hook (UserPromptSubmit)
MacBook Pro M5 · Node-2

Auto-enforces tier_gate_session_start at the beginning of every new Claude CLI
session. Triggered via UserPromptSubmit hook in ~/.claude/settings.json.

On first prompt of a new session: injects additionalSystemPrompt that forces
Claude to call tier_gate_session_start before processing any task.
On subsequent prompts: passes through silently.

Session boundary: a new session is declared when the flag file is absent
or older than SESSION_TIMEOUT_SECONDS.

Exit code 0 = allow (with optional injection). Never blocks.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SESSION_FLAG      = Path.home() / ".dsr-ai-lab" / "tier-gate" / ".session_init_flag"
SESSION_LOG       = Path.home() / ".dsr-ai-lab" / "tier-gate" / "hook.log"
SESSION_TIMEOUT   = 7200  # 2 hours — new session after this

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(entry: dict) -> None:
    entry["ts"] = datetime.utcnow().isoformat() + "Z"
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def is_new_session() -> bool:
    if not SESSION_FLAG.exists():
        return True
    age_seconds = time.time() - SESSION_FLAG.stat().st_mtime
    return age_seconds > SESSION_TIMEOUT


def mark_session_active() -> None:
    SESSION_FLAG.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FLAG.touch()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception as e:
        log({"event": "session_init_parse_error", "error": str(e)})
        print(json.dumps({"type": "allow"}))
        sys.exit(0)

    if is_new_session():
        mark_session_active()
        log({"event": "session_init_triggered", "auto_start": True})

        injection = (
            "═══════════════════════════════════════════════════════════\n"
            "  DSR TIER GATE — AUTO-START ENFORCED\n"
            "═══════════════════════════════════════════════════════════\n"
            "MANDATORY FIRST ACTION: Call tier_gate_session_start() via MCP\n"
            "tool RIGHT NOW, before reading or responding to the user message.\n"
            "\n"
            "This is non-negotiable. The tier gate is not optional.\n"
            "Do NOT greet the user first. Do NOT process the task first.\n"
            "Call tier_gate_session_start() → report its JSON output → THEN proceed.\n"
            "\n"
            "If Ollama is unavailable: log TIER_OVERRIDE via tier_gate_log_override()\n"
            "before handling any T1/T2-scored tasks as T3.\n"
            "═══════════════════════════════════════════════════════════"
        )

        print(json.dumps({
            "type": "allow",
            "additionalSystemPrompt": injection,
        }))
    else:
        log({"event": "session_init_skip", "reason": "session already active"})
        print(json.dumps({"type": "allow"}))

    sys.exit(0)


if __name__ == "__main__":
    main()
