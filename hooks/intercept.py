#!/usr/bin/env python3
"""
intercept.py — PreToolUse hook for Claude Tier System v10.1

Intercepts Edit/Write/MultiEdit/NotebookEdit tool calls from Claude (Brain),
classifies the task complexity, routes content generation to the appropriate
local Gemma 4 tier via Ollama's Anthropic-compatible API, and returns the
locally-generated content invisibly to Claude via hookSpecificOutput.updatedInput.

KEY MECHANICS:
  - T1 (gemma4:e4b)              : score 1-3, on-demand load (keep_alive=5m)
  - T2 (gemma4:26b)              : score 4-6, always warm (keep_alive=-1)
  - T3 (gemma4:26b + <|think|>)  : score 7-8, SAME loaded model as T2,
                                   thinking enabled by prepending <|think|>
                                   control token to system prompt
  - T-CLOUD primary (qwen3-coder:480b-cloud) : score 9-10
  - T-CLOUD fallback (gemma4:31b-cloud)      : auto-retry on primary failure

ALL DEPENDENCIES ARE STDLIB. No LangChain, no LangGraph, no httpx, no requests.

INPUT (stdin, JSON):
  {
    "session_id": "...",
    "cwd": "...",
    "hook_event_name": "PreToolUse",
    "tool_name": "Edit"|"Write"|"MultiEdit"|"NotebookEdit",
    "tool_input": {...},
    ...
  }

OUTPUT (stdout, JSON, exit 0):
  {
    "continue": true,
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow",
      "permissionDecisionReason": "Routed through ...",
      "updatedInput": {...}
    }
  }

ON FAILURE: passes through (exit 0, no rewrite). Never blocks Brain on hook
errors — the gate is a routing optimization, not a blocking security boundary.

VERSION: v10.1 (May 2026)
"""

import json
import os
import sys
import time
import sqlite3
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

T1_MODEL = os.environ.get("T1_MODEL", "gemma4:e4b")
T2_MODEL = os.environ.get("T2_MODEL", "gemma4:26b")
T3_MODEL = os.environ.get("T3_MODEL", "gemma4:26b")
T3_THINKING_TOKEN = os.environ.get("T3_THINKING_TOKEN", "<|think|>")

T_CLOUD_PRIMARY = os.environ.get("T_CLOUD_PRIMARY", "qwen3-coder:480b-cloud")
T_CLOUD_FALLBACK = os.environ.get("T_CLOUD_FALLBACK", "gemma4:31b-cloud")

LOG_DIR = Path(os.path.expanduser(os.environ.get("DSR_AI_LAB_LOG_DIR", "~/.dsr-ai-lab/logs")))
AUDIT_DB = Path(os.path.expanduser(os.environ.get("DSR_AI_LAB_AUDIT_DB", "~/.dsr-ai-lab/audit.db")))

LOG_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "intercept.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("intercept")


# ─────────────────────────────────────────────────────────────────────────
# Tier classifier (lightweight; deeper logic lives in tier-enforcer-mcp)
# ─────────────────────────────────────────────────────────────────────────

ARCH_KEYWORDS = (
    "architecture", "design pattern", "algorithm",
    "novel approach", "from scratch", "greenfield",
    "rewrite from", "migrate to", "scaffold a", "bootstrap a",
)

RCA_KEYWORDS = (
    "root cause", "rca", "deep debug", "race condition",
    "memory leak", "deadlock", "heisenbug", "intermittent",
)

PLATFORM_KEYWORDS = (
    "full platform", "entire system", "end to end system",
    "whole application", "full stack from",
)


def estimate_score(tool_name: str, tool_input: dict, cwd: str) -> int:
    """Heuristic 1–10 scoring based on tool name and input shape."""
    text_blob = json.dumps(tool_input).lower()
    score = 1

    # Tool-shape signals
    if tool_name == "MultiEdit":
        score = 5
        edits = tool_input.get("edits", [])
        if len(edits) > 5:
            score = 6
    elif tool_name == "NotebookEdit":
        score = 4
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        loc = content.count("\n")
        if loc > 200:
            score = 6
        elif loc > 50:
            score = 4
        else:
            score = 3
    elif tool_name == "Edit":
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        delta_lines = max(old.count("\n"), new.count("\n"))
        if delta_lines > 30:
            score = 5
        elif delta_lines > 5:
            score = 3
        else:
            score = 2

    # Keyword escalation
    if any(k in text_blob for k in PLATFORM_KEYWORDS):
        score = 10
    elif any(k in text_blob for k in ARCH_KEYWORDS):
        score = max(score, 8)
    elif any(k in text_blob for k in RCA_KEYWORDS):
        score = max(score, 7)

    return max(1, min(10, score))


def select_tier(score: int) -> tuple[str, str, bool]:
    """
    Map score → (tier_name, model_tag, thinking_enabled).
    T2 and T3 share the same model; only T3 has thinking enabled.
    """
    if score <= 3:
        return ("T1", T1_MODEL, False)
    if score <= 6:
        return ("T2", T2_MODEL, False)
    if score <= 8:
        return ("T3", T3_MODEL, True)   # same model as T2, but thinking ON
    return ("T-CLOUD", T_CLOUD_PRIMARY, False)


# ─────────────────────────────────────────────────────────────────────────
# Ollama dispatch (Anthropic-compatible /v1/messages)
# ─────────────────────────────────────────────────────────────────────────

EXECUTOR_SYSTEM_BASE = """\
You are a stateless local code executor in a tiered AI architecture. Brain (Claude) \
has decomposed a task and delegated this specific edit to you. You will not see the \
broader conversation; only what is in this prompt. Generate the requested code change \
with these rules:

1. Match the existing code style, naming conventions, and patterns visible in the context.
2. Do not invent APIs, function signatures, or library calls that aren't shown or standard.
3. Preserve existing imports, type hints, and docstrings unless explicitly asked to change them.
4. Output ONLY the exact tool input JSON for the edit. Do not narrate, explain, or wrap in markdown.

Return your response as a single JSON object matching the original tool_input schema, \
with the same keys but updated values reflecting the requested change.
"""


def build_system_prompt(thinking_enabled: bool) -> str:
    """
    For T3 (Gemma 4 thinking), prepend the <|think|> control token.
    Per Ollama's Gemma 4 model card: 'Thinking is enabled by including the
    <|think|> token at the start of the system prompt.'
    """
    if thinking_enabled:
        return f"{T3_THINKING_TOKEN}\n{EXECUTOR_SYSTEM_BASE}"
    return EXECUTOR_SYSTEM_BASE


def call_ollama_for_edit(
    model: str,
    tool_name: str,
    tool_input: dict,
    cwd: str,
    thinking_enabled: bool = False,
    timeout: int = 120,
    max_tokens: int = 4096,
) -> dict:
    """
    POST to Ollama's Anthropic-compatible /v1/messages endpoint.
    Returns the rewritten tool_input dict, or raises on failure.
    temperature=0 + top_p=0.9 give deterministic, fast code output.
    """
    user_msg = (
        f"Tool: {tool_name}\n"
        f"Working directory: {cwd}\n"
        f"Current tool input (Brain's request):\n```json\n"
        f"{json.dumps(tool_input, indent=2)}\n```\n\n"
        f"Generate the rewritten tool_input. Output JSON only."
    )

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 0.9,
        "messages": [{"role": "user", "content": user_msg}],
        "system": build_system_prompt(thinking_enabled),
    }

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())

    text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    if not text.strip():
        raise ValueError("Empty response from local executor")

    # Detect Gemma 4 thinking parser glitch (llama.cpp issue #21338)
    # The bug emits <unused49> token floods when thinking is enabled.
    if "<unused49>" in text:
        raise ValueError("Detected <unused49> flood (Gemma 4 thinking parser bug). Retry without thinking.")

    # Strip code fences if model wrapped output despite instructions
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    # If thinking was enabled, the model may have emitted <thought>...</thought>
    # blocks that we need to strip before JSON parsing
    if thinking_enabled:
        # Strip any <thought>...</thought> or <think>...</think> blocks
        for open_tag, close_tag in (("<thought>", "</thought>"), ("<think>", "</think>")):
            while open_tag in text and close_tag in text:
                start = text.index(open_tag)
                end = text.index(close_tag) + len(close_tag)
                text = (text[:start] + text[end:]).strip()

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Local executor returned non-object: {type(parsed)}")

    return parsed


def dispatch_with_fallback(
    tier: str,
    primary_model: str,
    tool_name: str,
    tool_input: dict,
    cwd: str,
    thinking_enabled: bool,
    timeout: int,
    max_tokens: int = 4096,
) -> tuple[dict | None, str, str | None, int]:
    """
    Dispatch with T-CLOUD fallback chain and Gemma-thinking degradation.

    Returns: (updated_input | None, model_used, error_msg, fallback_count)
    """
    attempts: list[tuple[str, bool]] = [(primary_model, thinking_enabled)]

    if tier == "T-CLOUD":
        # Primary failed → fall back to gemma4:31b-cloud
        attempts.append((T_CLOUD_FALLBACK, False))
    elif tier == "T3" and thinking_enabled:
        # Thinking parser glitch → retry without thinking
        attempts.append((primary_model, False))

    last_err = None
    for i, (model, thinking) in enumerate(attempts):
        try:
            result = call_ollama_for_edit(
                model, tool_name, tool_input, cwd,
                thinking_enabled=thinking, timeout=timeout, max_tokens=max_tokens,
            )
            return (result, model, None, i)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            log.warning(f"Attempt {i+1}/{len(attempts)} on {model} (thinking={thinking}) failed: {last_err}")

    return (None, attempts[-1][0], last_err, len(attempts))


# ─────────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────────

def init_audit_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL,
            session_id      TEXT,
            tool_name       TEXT    NOT NULL,
            file_path       TEXT,
            classify_score  INTEGER NOT NULL,
            tier            TEXT    NOT NULL,
            model           TEXT    NOT NULL,
            thinking        INTEGER DEFAULT 0,
            latency_ms      INTEGER,
            success         INTEGER NOT NULL,
            error_msg       TEXT,
            fallback_count  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_routing_ts ON routing_log(ts)")
    conn.commit()
    conn.close()


def write_audit_row(db_path: Path, **fields) -> None:
    try:
        conn = sqlite3.connect(str(db_path), timeout=2.0)
        conn.execute("""
            INSERT INTO routing_log (
                ts, session_id, tool_name, file_path,
                classify_score, tier, model, thinking,
                latency_ms, success, error_msg, fallback_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fields.get("ts"),
            fields.get("session_id"),
            fields.get("tool_name"),
            fields.get("file_path"),
            fields.get("classify_score"),
            fields.get("tier"),
            fields.get("model"),
            1 if fields.get("thinking") else 0,
            fields.get("latency_ms"),
            1 if fields.get("success") else 0,
            fields.get("error_msg"),
            fields.get("fallback_count", 0),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"Audit write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────
# Hook output helpers
# ─────────────────────────────────────────────────────────────────────────

def render_assigned_banner(tier: str, model: str, tool_name: str, file_path: str, score: int, thinking: bool) -> str:
    """Render a Task Assigned banner matching the executed_banner style."""
    fname = os.path.basename(file_path) if file_path else "?"
    tier_label = f"{tier} · {model}"
    if thinking:
        tier_label += " [thinking]"
    lines = [
        "┌─ Task Assigned ─────────────────────────────────────────────────────┐",
        f"│  →  Tool      {tool_name:<18} File: {fname:<22}│",
        f"│     Tier      {tier_label:<54}│",
        f"│     Score     {str(score) + '/10':<55}│",
        "└─────────────────────────────────────────────────────────────────────┘",
    ]
    return "\n".join(l[:72] for l in lines)


def emit_allow_with_rewrite(updated_input: dict, reason: str, banner: str = "") -> None:
    output = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
            "updatedInput": updated_input,
        },
    }
    if banner:
        output["hookSpecificOutput"]["additionalContext"] = f"\n```\n{banner}\n```\n"
        try:
            with open("/dev/tty", "w") as _tty:
                _tty.write("\n" + banner + "\n")
                _tty.flush()
        except (OSError, IOError):
            pass
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()


def emit_passthrough(reason: str) -> None:
    output = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        },
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def main() -> int:
    init_audit_db(AUDIT_DB)

    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log.error(f"Bad JSON on stdin: {e}")
        emit_passthrough("Hook failed to parse stdin; passthrough")
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    session_id = event.get("session_id", "")
    cwd = event.get("cwd", "")
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    score = estimate_score(tool_name, tool_input, cwd)
    tier, model, thinking = select_tier(score)

    log.info(
        f"Intercepted {tool_name} on {file_path} → score={score} tier={tier} "
        f"model={model} thinking={thinking}"
    )

    # Timeouts: T1=90s, T2=180s, T3=240s, T-CLOUD=300s
    timeout = 300 if tier == "T-CLOUD" else (240 if tier == "T3" else (180 if tier == "T2" else 90))
    # max_tokens per tier: T1 fast/small, T2 balanced, T3/T-CLOUD full
    max_tokens = 2048 if tier == "T1" else (4096 if tier == "T2" else 8192)

    t0 = time.time()
    updated_input, used_model, err, fallback_count = dispatch_with_fallback(
        tier=tier,
        primary_model=model,
        tool_name=tool_name,
        tool_input=tool_input,
        cwd=cwd,
        thinking_enabled=thinking,
        timeout=timeout,
        max_tokens=max_tokens,
    )
    latency_ms = int((time.time() - t0) * 1000)

    success = updated_input is not None

    write_audit_row(
        AUDIT_DB,
        ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
        session_id=session_id,
        tool_name=tool_name,
        file_path=file_path,
        classify_score=score,
        tier=tier,
        model=used_model,
        thinking=thinking and fallback_count == 0,  # thinking only counts if not degraded
        latency_ms=latency_ms,
        success=success,
        error_msg=err,
        fallback_count=fallback_count,
    )

    if success and updated_input:
        # Validate executor preserved required keys for the original tool
        required_by_tool = {
            "Edit": {"file_path", "old_string", "new_string"},
            "Write": {"file_path", "content"},
            "MultiEdit": {"file_path", "edits"},
            "NotebookEdit": {"notebook_path", "new_source"},
        }
        required = required_by_tool.get(tool_name, set())
        if not required.issubset(updated_input.keys()):
            log.warning(
                f"Executor missing required keys for {tool_name}; "
                f"got {list(updated_input.keys())}, need {required}. Falling back."
            )
            emit_passthrough(
                f"Local executor output missing required keys for {tool_name}; "
                "falling back to native"
            )
            return 0

        fname = os.path.basename(file_path) if file_path else tool_name
        thinking_tag = " [thinking]" if thinking and fallback_count == 0 else ""
        fallback_tag = f" [{fallback_count} fallback(s)]" if fallback_count > 0 else ""
        reason = (
            f"[gate] ✓ {tier} · {used_model}{thinking_tag}{fallback_tag} | "
            f"score={score}/10 | {latency_ms}ms | {fname}"
        )

        banner = render_assigned_banner(tier, model, tool_name, file_path, score, thinking)
        emit_allow_with_rewrite(updated_input, reason, banner)
    else:
        # Routing failed across all attempts → passthrough so Brain can
        # decide what to do (often: notify user, retry manually, or proceed
        # with native edit if the user explicitly authorizes).
        emit_passthrough(
            f"Local routing failed across {fallback_count} attempts ({err or 'unknown'}); "
            "falling back to native"
        )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log.exception("Unhandled exception in intercept hook")
        try:
            emit_passthrough(f"Hook crashed: {type(e).__name__}; falling back to native")
        except Exception:
            pass
        sys.exit(0)
