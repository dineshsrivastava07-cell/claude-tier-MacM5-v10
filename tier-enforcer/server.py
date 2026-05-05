#!/usr/bin/env python3
"""
tier-enforcer/server.py — Claude Tier System v10.1

FastMCP server exposing the tier classifier, router, prewarm, and audit tools.
Spawned as a stdio subprocess by Claude at session start.

KEY MECHANICS:
  - T1 / T2 / T3 / T-CLOUD routing
  - T3 = same model as T2 (gemma4:26b) with <|think|> control token prepended
  - T-CLOUD primary (qwen3-coder:480b-cloud) with auto-fallback to gemma4:31b-cloud
  - Gemma 4 thinking parser glitch detection (llama.cpp issue #21338)
    auto-degrades to non-thinking on detection

DEPENDENCIES: fastmcp + stdlib only. No LangChain, no LangGraph, no httpx.

VERSION: v10.1 (May 2026)
"""

import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP
except ImportError:
    sys.stderr.write("fastmcp not installed. Run: pip install fastmcp\n")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

T1_MODEL = os.environ.get("T1_MODEL", "gemma4:e4b")
T2_MODEL = os.environ.get("T2_MODEL", "gemma4:26b")
T3_MODEL = os.environ.get("T3_MODEL", "gemma4:26b")  # same as T2 by design
T3_THINKING_TOKEN = os.environ.get("T3_THINKING_TOKEN", "<|think|>")

T_CLOUD_PRIMARY = os.environ.get("T_CLOUD_PRIMARY", "qwen3-coder:480b-cloud")
T_CLOUD_FALLBACK = os.environ.get("T_CLOUD_FALLBACK", "gemma4:31b-cloud")

T1_KEEP_ALIVE = os.environ.get("T1_KEEP_ALIVE", "5m")
T2_KEEP_ALIVE = os.environ.get("T2_KEEP_ALIVE", "-1")

AUDIT_DB = Path(os.path.expanduser(
    os.environ.get("DSR_AI_LAB_AUDIT_DB", "~/.dsr-ai-lab/audit.db")
))
AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)


TIER_TO_MODEL = {
    "T1": (T1_MODEL, False),                   # (model, thinking_default)
    "T2": (T2_MODEL, False),
    "T3": (T3_MODEL, True),                    # SAME model as T2, thinking ON
    "T-CLOUD": (T_CLOUD_PRIMARY, False),
}


# ─────────────────────────────────────────────────────────────────────────
# Audit DB
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_routing_ts ON routing_log(ts)")
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
            fields.get("ts", time.strftime("%Y-%m-%dT%H:%M:%S")),
            fields.get("session_id"),
            fields.get("tool_name", "tier_enforcer.route"),
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
# Classifier
# ─────────────────────────────────────────────────────────────────────────

ARCH_KEYWORDS = (
    "architecture", "design pattern", "algorithm derivation",
    "novel approach", "from scratch", "rewrite from scratch",
    "scaffold a", "bootstrap a",
)
RCA_KEYWORDS = (
    "root cause", "rca", "deep debug", "race condition",
    "memory leak", "deadlock", "intermittent failure",
)
GREENFIELD_KEYWORDS = (
    "full platform", "entire system", "complete service from spec",
    "build the whole", "end to end system",
)


def _score_text(text: str) -> int:
    t = text.lower()
    if any(k in t for k in GREENFIELD_KEYWORDS):
        return 10
    if any(k in t for k in ARCH_KEYWORDS):
        return 8
    if any(k in t for k in RCA_KEYWORDS):
        return 7
    n_words = len(t.split())
    if n_words > 80: return 6
    if n_words > 40: return 5
    if n_words > 20: return 4
    if n_words > 10: return 3
    return 2


def select_tier(score: int) -> tuple[str, str, bool]:
    """Map score → (tier_name, model_tag, thinking_enabled)."""
    if score <= 3:  return ("T1", T1_MODEL, False)
    if score <= 6:  return ("T2", T2_MODEL, False)
    if score <= 8:  return ("T3", T3_MODEL, True)
    return ("T-CLOUD", T_CLOUD_PRIMARY, False)


# ─────────────────────────────────────────────────────────────────────────
# Ollama helpers
# ─────────────────────────────────────────────────────────────────────────

def _ollama_get(path: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _ollama_post_chat(payload: dict, timeout: float = 30.0) -> dict | None:
    """Native Ollama /api/chat (used for prewarm only — has keep_alive support)."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        sys.stderr.write(f"[tier-enforcer] /api/chat failed: {e}\n")
        return None


def model_loaded(model: str) -> bool:
    ps = _ollama_get("/api/ps") or {}
    return any(m.get("name", "").startswith(model) for m in ps.get("models", []))


def model_pulled(model: str) -> bool:
    tags = _ollama_get("/api/tags") or {}
    return any(m.get("name", "").startswith(model) for m in tags.get("models", []))


def warm_model(model: str, keep_alive: str = "-1", timeout: float = 120.0) -> bool:
    result = _ollama_post_chat({
        "model": model,
        "messages": [{"role": "user", "content": "ready"}],
        "stream": False,
        "keep_alive": keep_alive,
    }, timeout=timeout)
    return result is not None


# ─────────────────────────────────────────────────────────────────────────
# Edit dispatch (Anthropic-compat /v1/messages)
# ─────────────────────────────────────────────────────────────────────────

EXECUTOR_BASE_PROMPT = """\
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


def build_system(thinking_enabled: bool) -> str:
    """For Gemma 4: prepending <|think|> at start of system prompt enables thinking."""
    if thinking_enabled:
        return f"{T3_THINKING_TOKEN}\n{EXECUTOR_BASE_PROMPT}"
    return EXECUTOR_BASE_PROMPT


def call_executor(
    model: str,
    tool_name: str,
    tool_input: dict,
    cwd: str = "",
    thinking_enabled: bool = False,
    timeout: float = 120.0,
) -> dict:
    """POST to /v1/messages and return parsed tool_input."""
    user_msg = (
        f"Tool: {tool_name}\n"
        f"Working directory: {cwd}\n"
        f"Current tool input (Brain's request):\n```json\n"
        f"{json.dumps(tool_input, indent=2)}\n```\n\n"
        f"Generate the rewritten tool_input. Output JSON only."
    )

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/v1/messages",
        data=json.dumps({
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": user_msg}],
            "system": build_system(thinking_enabled),
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

    if not text.strip():
        raise ValueError("Empty response from local executor")

    # Detect Gemma 4 thinking parser glitch
    if "<unused49>" in text:
        raise ValueError("Detected <unused49> flood (llama.cpp issue #21338)")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()

    if thinking_enabled:
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
    tier: str, primary_model: str, tool_name: str, tool_input: dict,
    cwd: str, thinking_enabled: bool, timeout: int,
) -> tuple[dict | None, str, str | None, int]:
    """
    Dispatch with T-CLOUD fallback chain and Gemma-thinking degradation.
    Returns: (updated_input | None, model_used, error_msg, fallback_count)
    """
    attempts = [(primary_model, thinking_enabled)]
    if tier == "T-CLOUD":
        attempts.append((T_CLOUD_FALLBACK, False))
    elif tier == "T3" and thinking_enabled:
        attempts.append((primary_model, False))

    last_err = None
    for i, (model, thinking) in enumerate(attempts):
        try:
            result = call_executor(
                model, tool_name, tool_input, cwd,
                thinking_enabled=thinking, timeout=timeout,
            )
            return (result, model, None, i)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"

    return (None, attempts[-1][0], last_err, len(attempts))


# ─────────────────────────────────────────────────────────────────────────
# FastMCP server
# ─────────────────────────────────────────────────────────────────────────

mcp = FastMCP("tier-enforcer")


@mcp.tool()
def session_start() -> dict:
    """
    Mandatory first call. Verifies infrastructure liveness, prewarms T2.
    Returns: {status, components, warnings}
    """
    init_audit()
    status: dict[str, Any] = {"status": "READY", "warnings": [], "components": {}}

    tags = _ollama_get("/api/tags")
    if tags is None:
        status["status"] = "DEGRADED"
        status["warnings"].append(
            f"Ollama unreachable at {OLLAMA_HOST}. Start Ollama.app or run `ollama serve`."
        )
        status["components"]["ollama"] = "DOWN"
    else:
        status["components"]["ollama"] = "UP"

    # Verify all 4 models registered
    models_to_check = {
        "T1": T1_MODEL,
        "T2": T2_MODEL,
        "T-CLOUD-primary": T_CLOUD_PRIMARY,
        "T-CLOUD-fallback": T_CLOUD_FALLBACK,
    }
    # T3 reuses T2 — not a separate check
    for label, model in models_to_check.items():
        is_pulled = model_pulled(model)
        status["components"][f"{label}_pulled"] = is_pulled
        if not is_pulled:
            status["warnings"].append(f"{label}: {model} not pulled. Run `ollama pull {model}`.")
            if label == "T2":
                status["status"] = "DEGRADED"

    # Prewarm T2 (the workhorse). T1 stays cold; loads on demand.
    if status["components"].get("ollama") == "UP" and status["components"].get("T2_pulled"):
        threading.Thread(target=warm_model, args=(T2_MODEL, T2_KEEP_ALIVE), daemon=True).start()
        status["components"]["T2_warming"] = True

    status["info"] = (
        f"T3 reuses T2 model ({T2_MODEL}) with '{T3_THINKING_TOKEN}' control token. "
        f"T-CLOUD: primary={T_CLOUD_PRIMARY}, fallback={T_CLOUD_FALLBACK}."
    )

    return status


@mcp.tool()
def classify(task_text: str, file_count: int = 1, line_change_estimate: int = 0) -> dict:
    """
    Score a task 1-10 and return tier + model assignment.
    Returns: {score, tier, model, thinking, reasoning}
    """
    score = _score_text(task_text)

    if file_count >= 5:
        score = max(score, 6)
    elif file_count >= 3:
        score = max(score, 5)
    elif file_count == 2:
        score = max(score, 4)

    if line_change_estimate > 500:
        score = max(score, 7)
    elif line_change_estimate > 200:
        score = max(score, 6)
    elif line_change_estimate > 50:
        score = max(score, 4)

    score = max(1, min(10, score))
    tier, model, thinking = select_tier(score)

    return {
        "score": score,
        "tier": tier,
        "model": model,
        "thinking": thinking,
        "reasoning": (
            f"Task scored {score}/10 (text length, file_count={file_count}, "
            f"line_change_estimate={line_change_estimate}). "
            f"Routed to {tier} ({model}{', thinking=on' if thinking else ''})."
        ),
    }


@mcp.tool()
def route_edit(
    tool_name: str,
    tool_input: dict,
    classify_score: int = 0,
    cwd: str = "",
    session_id: str = "",
) -> dict:
    """
    Dispatch tool input to appropriate tier model and return rewritten input.
    Used by dsr-executor-mcp (Desktop) and as a fallback callable by hooks.

    Returns: {success, updated_input, tier, model, thinking, latency_ms, fallback_count, error}
    """
    if classify_score <= 0:
        classify_score = _score_text(json.dumps(tool_input))
    tier, model, thinking = select_tier(classify_score)

    timeout = 300 if tier == "T-CLOUD" else (180 if tier == "T3" else 120)
    t0 = time.time()

    updated, used_model, err, fallback_count = dispatch_with_fallback(
        tier=tier, primary_model=model, tool_name=tool_name, tool_input=tool_input,
        cwd=cwd, thinking_enabled=thinking, timeout=timeout,
    )
    latency = int((time.time() - t0) * 1000)
    success = updated is not None

    write_audit(
        session_id=session_id,
        tool_name=tool_name,
        file_path=(tool_input.get("file_path") or tool_input.get("notebook_path") or ""),
        classify_score=classify_score,
        tier=tier,
        model=used_model,
        thinking=thinking and fallback_count == 0,
        latency_ms=latency,
        success=success,
        error_msg=err,
        fallback_count=fallback_count,
    )

    return {
        "success": success,
        "updated_input": updated,
        "tier": tier,
        "model": used_model,
        "thinking": thinking and fallback_count == 0,
        "latency_ms": latency,
        "fallback_count": fallback_count,
        "error": err,
    }


@mcp.tool()
def prewarm(tier: str) -> dict:
    """Prewarm a tier's model into Ollama RAM. T1='5m', T2='-1', T-CLOUD ignored."""
    if tier not in TIER_TO_MODEL:
        return {"success": False, "error": f"Unknown tier: {tier}"}
    if tier == "T-CLOUD":
        return {"success": True, "note": "T-CLOUD is on Ollama Cloud; no local warmup needed."}
    if tier == "T3":
        # T3 reuses T2's loaded model
        tier = "T2"
    model, _ = TIER_TO_MODEL[tier]
    keep_alive = T1_KEEP_ALIVE if tier == "T1" else T2_KEEP_ALIVE
    ok = warm_model(model, keep_alive=keep_alive)
    return {"success": ok, "tier": tier, "model": model, "keep_alive": keep_alive}


@mcp.tool()
def tier_health() -> dict:
    """Liveness map: which tier models are pulled and currently loaded."""
    tags = _ollama_get("/api/tags") or {}
    ps = _ollama_get("/api/ps") or {}
    pulled_set = {m.get("name", "") for m in tags.get("models", [])}
    loaded_set = {m.get("name", "") for m in ps.get("models", [])}

    out = {}
    for label, model in (
        ("T1", T1_MODEL),
        ("T2", T2_MODEL),
        ("T-CLOUD-primary", T_CLOUD_PRIMARY),
        ("T-CLOUD-fallback", T_CLOUD_FALLBACK),
    ):
        is_pulled = any(name.startswith(model) for name in pulled_set)
        is_loaded = any(name.startswith(model) for name in loaded_set)
        out[label] = {"model": model, "pulled": is_pulled, "loaded": is_loaded}
    out["T3"] = {
        "model": T3_MODEL,
        "note": "T3 reuses T2's loaded model with " + T3_THINKING_TOKEN + " token; same RAM",
    }
    return out


@mcp.tool()
def audit_summary(window_hours: int = 24) -> dict:
    """Recent routing stats from the audit DB."""
    if not AUDIT_DB.exists():
        return {"error": "audit DB not initialized"}
    try:
        conn = sqlite3.connect(str(AUDIT_DB), timeout=2.0)
        cur = conn.execute(f"""
            SELECT tier, COUNT(*), AVG(latency_ms),
                   SUM(success), SUM(1 - success), SUM(thinking),
                   SUM(CASE WHEN fallback_count > 0 THEN 1 ELSE 0 END)
            FROM routing_log
            WHERE ts >= datetime('now', '-{int(window_hours)} hours')
            GROUP BY tier
        """)
        rows = cur.fetchall()
        conn.close()
        return {
            "window_hours": window_hours,
            "by_tier": [
                {
                    "tier": r[0],
                    "n_calls": r[1],
                    "avg_latency_ms": round(r[2] or 0, 1),
                    "successes": r[3] or 0,
                    "failures": r[4] or 0,
                    "thinking_enabled_count": r[5] or 0,
                    "fallback_invoked_count": r[6] or 0,
                }
                for r in rows
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def log_override(reason: str, original_tier: str, override_tier: str, session_id: str = "") -> dict:
    """Log when user manually overrides a tier assignment via /tier slash command."""
    model = TIER_TO_MODEL.get(override_tier, ("?", False))[0]
    write_audit(
        session_id=session_id,
        tool_name="tier_override",
        file_path=None,
        classify_score=0,
        tier=override_tier,
        model=model,
        latency_ms=0,
        success=True,
        error_msg=f"Override from {original_tier}: {reason}",
    )
    return {"logged": True}


# ─────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_audit()
    mcp.run()
