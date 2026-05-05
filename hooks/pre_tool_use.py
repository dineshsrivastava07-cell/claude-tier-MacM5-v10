#!/usr/bin/env python3
"""
DSR AI-Lab · PreToolUse Hook
MacBook Pro M5 · Node-2

Hard gate enforcement at the Claude CLI hook layer.
Intercepts every tool call and enforces tier gate rules before execution.

Claude CLI invokes this script via stdin/stdout per the hooks spec.
Exit code 0 = allow. Exit code 2 = block (with message to Claude).
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HOOK_LOG = Path.home() / ".dsr-ai-lab" / "tier-gate" / "hook.log"
HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)


def log(entry: dict) -> None:
    entry["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(HOOK_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def block(reason: str, advice: str = "") -> None:
    """Emit a block response and exit with code 2."""
    response = {
        "type": "block",
        "message": f"[TIER_GATE_BLOCK] {reason}",
    }
    if advice:
        response["message"] += f"\n\nREQUIRED ACTION: {advice}"
    print(json.dumps(response))
    log({"event": "block", "reason": reason})
    sys.exit(2)


def allow(note: str = "") -> None:
    """Emit allow response and exit with code 0."""
    response = {"type": "allow"}
    if note:
        response["note"] = note
    print(json.dumps(response))
    log({"event": "allow", "note": note})
    sys.exit(0)


# ── Dangerous command patterns ────────────────────────────────────────────────

DESTRUCTIVE_PATTERNS = [
    (r"\brm\s+-rf\b", "rm -rf detected"),
    (r"\bdrop\s+table\b", "DROP TABLE detected"),
    (r"\bdelete\s+from\b", "DELETE FROM without WHERE suspected"),
    (r"\bchmod\s+777\b", "chmod 777 detected"),
    (r"\bcurl\s+.*\|\s*sh\b", "curl|sh pipe detected"),
    (r"\beval\s*\(", "eval() call detected"),
    (r"\b__import__\s*\(", "__import__ call detected"),
    (r"\bos\.system\b", "os.system() call detected"),
    (r"\bsubprocess\.call\b.*shell\s*=\s*True", "shell=True subprocess detected"),
]

SECRET_LEAK_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "Anthropic API key pattern detected"),
    (r"ANTHROPIC_API_KEY\s*=\s*['\"]?sk-", "API key assignment detected"),
    (r"password\s*=\s*['\"][^'\"]{4,}['\"]", "Hardcoded password detected"),
    (r"Bearer\s+[a-zA-Z0-9\-_]{20,}", "Bearer token in payload detected"),
]

CLAUDE_MD_SELF_MODIFY_PATTERNS = [
    (r"CLAUDE\.md", "CLAUDE.md modification attempt"),
]


# ── Tool-specific gate rules ──────────────────────────────────────────────────

def check_bash_tool(tool_input: dict) -> None:
    command = tool_input.get("command", "")

    for pattern, label in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            block(
                reason=f"Destructive shell command blocked: {label}",
                advice=(
                    "Show the command to the user and ask for explicit confirmation "
                    "before proceeding. Do NOT auto-execute destructive commands."
                ),
            )

    for pattern, label in SECRET_LEAK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            block(
                reason=f"Secret/credential exposure risk: {label}",
                advice=(
                    "Remove credentials from the command. Use environment variables "
                    "or macOS Keychain references instead."
                ),
            )


def check_write_tool(tool_input: dict) -> None:
    file_path = tool_input.get("path", "") or tool_input.get("file_path", "")
    content = tool_input.get("content", "") or tool_input.get("new_str", "")

    # Block CLAUDE.md modification
    if "CLAUDE.md" in file_path:
        block(
            reason="Attempted self-modification of CLAUDE.md during session.",
            advice=(
                "CLAUDE.md cannot be modified during an active session. "
                "Edit it manually outside Claude CLI."
            ),
        )

    # Check for secret leakage in file writes
    for pattern, label in SECRET_LEAK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            block(
                reason=f"Secret/credential in file write blocked: {label}",
                advice=(
                    "Do not write credentials to files. Use .env with gitignore, "
                    "or macOS Keychain for secret storage."
                ),
            )


def check_edit_tool(tool_input: dict) -> None:
    # Edit tool also has new_str and path — reuse write checks
    check_write_tool(tool_input)


def check_tier_gate_run(tool_name: str, tool_input: dict) -> None:
    """
    Validate that tier_gate_run_t1 / _t2 are only called when appropriate.
    We can't fully enforce tier scoring here (the MCP server does that),
    but we can block obvious misuse patterns.
    """
    prompt = tool_input.get("prompt", "")

    # Block T1 being used for security/auth tasks
    if "run_t1" in tool_name:
        for pattern, _ in [
            (r"\b(auth|oauth|jwt|encrypt|decrypt|secret|password)\b", "security"),
            (r"\b(architecture|design|multi-service)\b", "architecture"),
        ]:
            if re.search(pattern, prompt, re.IGNORECASE):
                block(
                    reason=f"T1 tool called with task beyond T1 skill domain.",
                    advice=(
                        "Call tier_gate_classify first. If score ≥ 4, route to T2 or T3. "
                        "T1 must not handle security, authentication, or architecture tasks."
                    ),
                )


# ── Main hook dispatcher ──────────────────────────────────────────────────────

def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        # Malformed input — allow (don't break Claude with hook parse errors)
        log({"event": "parse_error", "error": str(e)})
        allow(note="hook parse error — allowing")
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    log({
        "event": "pre_tool_use",
        "tool_name": tool_name,
        "input_keys": list(tool_input.keys()),
    })

    # Route to tool-specific checks
    if tool_name in ("bash", "computer", "shell"):
        check_bash_tool(tool_input)

    elif tool_name in ("write", "create_file", "file_write"):
        check_write_tool(tool_input)

    elif tool_name in ("edit", "str_replace_editor", "str_replace"):
        check_edit_tool(tool_input)

    elif "tier_gate_run" in tool_name:
        check_tier_gate_run(tool_name, tool_input)

    # Allow all other tools (read, search, MCP tools, etc.)
    allow()


if __name__ == "__main__":
    main()
