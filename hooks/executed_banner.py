#!/usr/bin/env python3
"""
executed_banner.py — PostToolUse hook for Claude Tier System v10.1

Fires after Edit/Write/MultiEdit/NotebookEdit completes. Reads the most recent
routing_log entry for this session from the audit DB and emits an execution
summary banner as additionalContext so Claude and the user know which tier
handled the edit and how long it took.

If audit DB is unavailable or no entry found, emits a minimal passthrough.

DEPENDENCIES: stdlib only.
VERSION: v10.1 (May 2026)
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path


AUDIT_DB = Path(os.path.expanduser(
    os.environ.get("DSR_AI_LAB_AUDIT_DB", "~/.dsr-ai-lab/audit.db")
))

TIER_COLORS = {
    "T1": "T1 · gemma4:e4b",
    "T2": "T2 · gemma4:26b",
    "T3": "T3 · gemma4:26b + <|think|>",
    "T-CLOUD": "T-CLOUD · qwen3-coder:480b-cloud",
}


def last_routing_row(session_id: str) -> dict | None:
    """Return the most recent routing_log row for this session, or None."""
    if not AUDIT_DB.exists():
        return None
    try:
        conn = sqlite3.connect(str(AUDIT_DB), timeout=2.0)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT tier, model, latency_ms, success, error_msg,
                   fallback_count, thinking, tool_name, file_path
            FROM routing_log
            WHERE session_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (session_id,),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def render_banner(row: dict, tool_name: str, file_path: str) -> str:
    tier = row.get("tier", "?")
    model = row.get("model", "?")
    latency = row.get("latency_ms", 0)
    success = bool(row.get("success", False))
    thinking = bool(row.get("thinking", False))
    fallbacks = row.get("fallback_count", 0)

    status_icon = "✓" if success else "✗"
    tier_label = TIER_COLORS.get(tier, f"{tier} · {model}")
    if thinking:
        tier_label += " [thinking]"
    if fallbacks:
        tier_label += f" [{fallbacks} fallback(s)]"

    fname = Path(file_path).name if file_path else "?"
    latency_str = f"{latency}ms" if latency < 10000 else f"{latency//1000}s"

    lines = [
        "┌─ Executed ──────────────────────────────────────────────────────────┐",
        f"│  {status_icon}  Tool      {tool_name:<18} File: {fname:<22}│",
        f"│     Tier      {tier_label:<54}│",
        f"│     Latency   {latency_str:<54}│",
        "└─────────────────────────────────────────────────────────────────────┘",
    ]
    # Trim each line to 72 chars interior + borders
    return "\n".join(l[:72] for l in lines)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        # Never block on hook errors
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    session_id = event.get("session_id", "")
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    row = last_routing_row(session_id)

    if row:
        banner = render_banner(row, tool_name, file_path)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"\n```\n{banner}\n```\n",
            }
        }
    else:
        # No DB entry (e.g., passthrough on Gemma failure) — minimal notice
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"[gate] {tool_name} completed (no routing entry — native passthrough)\n",
            }
        }

    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        sys.stdout.write(json.dumps({"continue": True}))
        sys.exit(0)
