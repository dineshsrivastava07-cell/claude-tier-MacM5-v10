#!/usr/bin/env python3
"""
dsr-executor-mcp/server.py — Claude Tier System v10.1

Bridges Claude Desktop (which lacks PreToolUse hooks) to the local Gemma
executor pool. Exposes local_edit, local_write, local_multiedit MCP tools
that Brain calls in lieu of the (disabled) native Edit/Write/MultiEdit tools.

KEY MECHANICS:
  - Inline classifier (avoids stdio-to-stdio MCP recursion)
  - T3 = same model as T2 with <|think|> control token
  - T-CLOUD primary → fallback chain
  - Backup before overwrite (.bak file)

DEPENDENCIES: fastmcp + stdlib only.
VERSION: v10.1 (May 2026)
"""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from fastmcp import FastMCP
except ImportError:
    sys.stderr.write("fastmcp not installed. Run: pip install fastmcp\n")
    sys.exit(1)


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

T1_MODEL = os.environ.get("T1_MODEL", "gemma4:e4b")
T2_MODEL = os.environ.get("T2_MODEL", "gemma4:26b")
T3_MODEL = os.environ.get("T3_MODEL", "gemma4:26b")
T3_THINKING_TOKEN = os.environ.get("T3_THINKING_TOKEN", "<|think|>")

T_CLOUD_PRIMARY = os.environ.get("T_CLOUD_PRIMARY", "qwen3-coder:480b-cloud")
T_CLOUD_FALLBACK = os.environ.get("T_CLOUD_FALLBACK", "gemma4:31b-cloud")

AUDIT_DB = Path(os.path.expanduser(
    os.environ.get("DSR_AI_LAB_AUDIT_DB", "~/.dsr-ai-lab/audit.db")
))
AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────
# Audit (shared schema with tier-enforcer)
# ─────────────────────────────────────────────────────────────────────────

def init_audit() -> None:
    conn = sqlite3.connect(str(AUDIT_DB))
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
    conn.commit()
    conn.close()


def write_audit(**fields) -> None:
    try:
        conn = sqlite3.connect(str(AUDIT_DB), timeout=2.0)
        conn.execute("""
            INSERT INTO routing_log (
                ts, session_id, tool_name, file_path,
                classify_score, tier, model, thinking,
                latency_ms, success, error_msg, fallback_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            fields.get("session_id", "desktop"),
            fields.get("tool_name", "?"),
            fields.get("file_path"),
            fields.get("classify_score", 0),
            fields.get("tier", "?"),
            fields.get("model", "?"),
            1 if fields.get("thinking") else 0,
            fields.get("latency_ms", 0),
            1 if fields.get("success") else 0,
            fields.get("error_msg"),
            fields.get("fallback_count", 0),
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# Inline classifier + Ollama dispatch
# ─────────────────────────────────────────────────────────────────────────

ARCH_KEYWORDS = (
    "architecture", "design pattern", "algorithm derivation",
    "novel approach", "from scratch", "scaffold a", "bootstrap a",
)
RCA_KEYWORDS = (
    "root cause", "rca", "deep debug", "race condition",
    "memory leak", "deadlock",
)
GREENFIELD_KEYWORDS = (
    "full platform", "entire system", "complete service from spec",
)


def score_text(text: str, file_count: int = 1) -> int:
    t = text.lower()
    if any(k in t for k in GREENFIELD_KEYWORDS): return 10
    if any(k in t for k in ARCH_KEYWORDS):       return 8
    if any(k in t for k in RCA_KEYWORDS):        return 7
    n = len(t.split())
    base = 2
    if n > 80:   base = 6
    elif n > 40: base = 5
    elif n > 20: base = 4
    elif n > 10: base = 3
    if file_count >= 5:   base = max(base, 6)
    elif file_count >= 3: base = max(base, 5)
    elif file_count == 2: base = max(base, 4)
    return max(1, min(10, base))


def select_tier(score: int) -> tuple[str, str, bool]:
    """Returns (tier, model, thinking_enabled)."""
    if score <= 3:  return ("T1", T1_MODEL, False)
    if score <= 6:  return ("T2", T2_MODEL, False)
    if score <= 8:  return ("T3", T3_MODEL, True)
    return ("T-CLOUD", T_CLOUD_PRIMARY, False)


EXECUTOR_BASE = """\
You are a stateless local code executor. Brain (Claude) has delegated this \
specific edit to you. You will not see the broader conversation; only what is \
in this prompt. Generate the requested change with these rules:

1. Match existing code style, naming conventions, and patterns.
2. Do not invent APIs, function signatures, or library calls.
3. Preserve existing imports, type hints, and docstrings unless asked otherwise.
4. Output ONLY the rewritten file content (or the requested code segment).
5. Do not narrate, explain, or wrap in markdown code fences.
"""


def build_system(thinking_enabled: bool) -> str:
    if thinking_enabled:
        return f"{T3_THINKING_TOKEN}\n{EXECUTOR_BASE}"
    return EXECUTOR_BASE


def call_ollama(model: str, system_msg: str, user_msg: str, timeout: float = 120.0) -> str:
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/v1/messages",
        data=json.dumps({
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": user_msg}],
            "system": system_msg,
        }).encode(),
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
    text = text.strip()

    if "<unused49>" in text:
        raise ValueError("Detected <unused49> flood (llama.cpp issue #21338)")

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    # Strip thought blocks if present
    for open_tag, close_tag in (("<thought>", "</thought>"), ("<think>", "</think>")):
        while open_tag in text and close_tag in text:
            start = text.index(open_tag)
            end = text.index(close_tag) + len(close_tag)
            text = (text[:start] + text[end:]).strip()

    return text


def call_with_fallback(
    tier: str, primary_model: str, system_msg: str, user_msg: str,
    thinking_enabled: bool, timeout: float,
) -> tuple[str, str, int, str | None]:
    """Returns: (content, model_used, fallback_count, error_msg)."""
    attempts = [(primary_model, thinking_enabled)]
    if tier == "T-CLOUD":
        attempts.append((T_CLOUD_FALLBACK, False))
    elif tier == "T3" and thinking_enabled:
        attempts.append((primary_model, False))

    last_err = None
    for i, (model, thinking) in enumerate(attempts):
        try:
            sys_msg = build_system(thinking)
            content = call_ollama(model, sys_msg, user_msg, timeout=timeout)
            if not content:
                raise ValueError("Empty response")
            return (content, model, i, None)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

    return ("", attempts[-1][0], len(attempts), last_err)


# ─────────────────────────────────────────────────────────────────────────
# FastMCP server
# ─────────────────────────────────────────────────────────────────────────

mcp = FastMCP("dsr-executor")


@mcp.tool()
def local_edit(
    path: str,
    instructions: str,
    context: str = "",
    session_id: str = "desktop",
) -> dict:
    """
    Modify an existing file via local Gemma executor.

    Args:
      path:         absolute or project-relative path to the file
      instructions: clear intent from Brain about what to change and why
      context:      relevant surrounding code, interface contracts, naming conventions;
                    the executor sees ONLY this and `instructions`, not the broader conversation
      session_id:   for audit logging
    """
    init_audit()
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}. Use local_write."}

    score = score_text(instructions, file_count=1)
    tier, model, thinking = select_tier(score)

    current_content = file_path.read_text(encoding="utf-8", errors="replace")

    user_msg = (
        f"FILE: {file_path}\n\n"
        f"CURRENT CONTENT:\n```\n{current_content}\n```\n\n"
        f"BRAIN'S INSTRUCTIONS:\n{instructions}\n\n"
    )
    if context:
        user_msg += f"ADDITIONAL CONTEXT:\n{context}\n\n"
    user_msg += (
        "Generate the COMPLETE rewritten file content. "
        "Output ONLY the file content, no narration or fences."
    )

    timeout = 300.0 if tier == "T-CLOUD" else (180.0 if tier == "T3" else 120.0)
    t0 = time.time()
    new_content, used_model, fallback_count, err = call_with_fallback(
        tier=tier, primary_model=model,
        system_msg="",  # built inside call_with_fallback
        user_msg=user_msg, thinking_enabled=thinking, timeout=timeout,
    )
    latency = int((time.time() - t0) * 1000)

    if not new_content:
        write_audit(
            session_id=session_id, tool_name="local_edit",
            file_path=str(file_path), classify_score=score,
            tier=tier, model=used_model, thinking=thinking,
            latency_ms=latency, success=False, error_msg=err,
            fallback_count=fallback_count,
        )
        return {"success": False, "error": err, "tier": tier, "model": used_model}

    # Backup before overwrite
    backup = file_path.with_suffix(file_path.suffix + ".bak")
    backup.write_text(current_content, encoding="utf-8")
    file_path.write_text(new_content, encoding="utf-8")

    write_audit(
        session_id=session_id, tool_name="local_edit",
        file_path=str(file_path), classify_score=score,
        tier=tier, model=used_model,
        thinking=thinking and fallback_count == 0,
        latency_ms=latency, success=True,
        fallback_count=fallback_count,
    )

    return {
        "success": True,
        "path": str(file_path),
        "backup": str(backup),
        "tier": tier,
        "model": used_model,
        "thinking": thinking and fallback_count == 0,
        "score": score,
        "latency_ms": latency,
        "fallback_count": fallback_count,
    }


@mcp.tool()
def local_write(
    path: str,
    intent: str,
    context: str = "",
    session_id: str = "desktop",
) -> dict:
    """Create a new file via local Gemma executor."""
    init_audit()
    file_path = Path(path).expanduser().resolve()
    if file_path.exists():
        return {"success": False, "error": f"File already exists: {file_path}. Use local_edit."}

    file_path.parent.mkdir(parents=True, exist_ok=True)

    score = score_text(intent, file_count=1)
    tier, model, thinking = select_tier(score)

    user_msg = (
        f"NEW FILE TO CREATE: {file_path}\n\n"
        f"BRAIN'S INTENT:\n{intent}\n\n"
    )
    if context:
        user_msg += f"CONTEXT:\n{context}\n\n"
    user_msg += "Generate the COMPLETE file content. Output ONLY the content, no fences."

    timeout = 300.0 if tier == "T-CLOUD" else (180.0 if tier == "T3" else 120.0)
    t0 = time.time()
    content, used_model, fallback_count, err = call_with_fallback(
        tier=tier, primary_model=model, system_msg="",
        user_msg=user_msg, thinking_enabled=thinking, timeout=timeout,
    )
    latency = int((time.time() - t0) * 1000)

    if not content:
        write_audit(
            session_id=session_id, tool_name="local_write",
            file_path=str(file_path), classify_score=score,
            tier=tier, model=used_model, thinking=thinking,
            latency_ms=latency, success=False, error_msg=err,
            fallback_count=fallback_count,
        )
        return {"success": False, "error": err, "tier": tier, "model": used_model}

    file_path.write_text(content, encoding="utf-8")

    write_audit(
        session_id=session_id, tool_name="local_write",
        file_path=str(file_path), classify_score=score,
        tier=tier, model=used_model,
        thinking=thinking and fallback_count == 0,
        latency_ms=latency, success=True,
        fallback_count=fallback_count,
    )

    return {
        "success": True,
        "path": str(file_path),
        "tier": tier, "model": used_model,
        "thinking": thinking and fallback_count == 0,
        "score": score,
        "latency_ms": latency,
        "fallback_count": fallback_count,
    }


@mcp.tool()
def local_multiedit(
    operations: list[dict],
    coordinated_intent: str = "",
    session_id: str = "desktop",
) -> dict:
    """Apply coordinated edits across multiple files."""
    init_audit()
    if not operations:
        return {"success": False, "error": "No operations provided"}

    n = len(operations)
    score = score_text(coordinated_intent or operations[0].get("instructions", ""), file_count=n)
    score = max(score, 5 if n >= 3 else 4)
    tier, model, thinking = select_tier(score)

    results = []
    overall_success = True
    t0 = time.time()

    for op in operations:
        path = op.get("path", "")
        instructions = op.get("instructions", "")
        context = op.get("context", "")
        if not path or not instructions:
            results.append({"success": False, "error": "Missing path or instructions"})
            overall_success = False
            continue

        prepended_context = (
            f"COORDINATED MULTI-FILE EDIT — overall intent:\n{coordinated_intent}\n\n"
            f"This is one operation in a set of {n}. "
            f"Maintain naming/style consistency with sibling operations.\n\n"
            f"{context}"
        )

        file_path = Path(path).expanduser().resolve()
        if file_path.exists():
            r = local_edit(str(file_path), instructions, prepended_context, session_id)
        else:
            r = local_write(str(file_path), instructions, prepended_context, session_id)

        results.append(r)
        if not r.get("success"):
            overall_success = False

    latency = int((time.time() - t0) * 1000)

    return {
        "success": overall_success,
        "n_operations": n,
        "tier": tier,
        "model": model,
        "thinking": thinking,
        "score": score,
        "latency_ms": latency,
        "results": results,
    }


@mcp.tool()
def health() -> dict:
    """Quick liveness check for the executor."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2.0) as r:
            tags = json.loads(r.read().decode())
        return {
            "status": "ok",
            "ollama": "up",
            "n_models_pulled": len(tags.get("models", [])),
            "tiers": {
                "T1": T1_MODEL,
                "T2": T2_MODEL,
                "T3": f"{T3_MODEL} + {T3_THINKING_TOKEN}",
                "T-CLOUD-primary": T_CLOUD_PRIMARY,
                "T-CLOUD-fallback": T_CLOUD_FALLBACK,
            },
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


if __name__ == "__main__":
    init_audit()
    mcp.run()
