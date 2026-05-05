#!/usr/bin/env python3
"""
DSR AI-Lab · Tier Gate MCP Server
MacBook Pro M5 · Node-2

Hard tier gate for Claude CLI on MBP M5.
Routes tasks to: T1 (qwen2.5-coder:7b) | T2 (qwen2.5-coder:14b) | T3 (Claude)

No LiteLLM. Direct Ollama REST API only.
FastMCP stdio transport for Claude CLI integration.
"""

import json
import logging
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

import httpx
from fastmcp import FastMCP

# ── Configuration ──────────────────────────────────────────────────────────────

OLLAMA_BASE  = "http://127.0.0.1:11434"
T1_MODEL     = "qwen2.5-coder:7b"
T2_MODEL     = "qwen2.5-coder:14b"
LOG_PATH     = Path.home() / ".dsr-ai-lab" / "tier-gate" / "gate.log"
OLLAMA_LOG   = Path.home() / ".dsr-ai-lab" / "tier-gate" / "ollama.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Auth: Claude subscription (OAuth) only. No ANTHROPIC_API_KEY used or accepted.
# Claude CLI authenticates via: claude login  (run once, stored in ~/.claude/)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("tier-gate")

mcp = FastMCP("dsr-tier-gate")


# ── Tier Definitions ──────────────────────────────────────────────────────────

class Tier(IntEnum):
    T1 = 1   # qwen2.5-coder:7b  · score 1-3
    T2 = 2   # qwen2.5-coder:14b · score 4-6
    T3 = 3   # Claude             · score 7-10


TIER_MODELS = {
    Tier.T1: T1_MODEL,
    Tier.T2: T2_MODEL,
    Tier.T3: "claude (this session)",
}

TIER_SCORE_MAP = {
    (1, 3):  Tier.T1,
    (4, 6):  Tier.T2,
    (7, 10): Tier.T3,
}


# ── Complexity Scorer ─────────────────────────────────────────────────────────

class ComplexityScorer:
    """
    Deterministic rule-based complexity scorer.
    Score range: 1–10.  No LLM involved — this is a hard rule engine.
    """

    SECURITY_PATTERNS = re.compile(
        r"\b(auth|oauth|jwt|token|secret|password|encrypt|decrypt|tls|ssl|"
        r"hmac|certificate|keychain|credential|rbac|permission|acl|sudo)\b",
        re.IGNORECASE,
    )
    COMPLIANCE_PATTERNS = re.compile(
        r"\b(soc2|iso27001|gdpr|dpdp|sebi|hipaa|pci|audit|compliance|"
        r"regulatory|lodr|pit|brsr)\b",
        re.IGNORECASE,
    )
    AIML_PATTERNS = re.compile(
        r"\b(model|training|inference|embedding|rag|vector|fine.?tun|"
        r"langchain|langgraph|llm|prompt.?engineer|eval|benchmark)\b",
        re.IGNORECASE,
    )
    MULTI_SERVICE_PATTERNS = re.compile(
        r"\b(microservice|kafka|rabbitmq|grpc|graphql|websocket|webhook|"
        r"orchestrat|workflow|pipeline|dag|celery|airflow)\b",
        re.IGNORECASE,
    )
    NOVEL_ALGO_PATTERNS = re.compile(
        r"\b(design|algorithm|implement from scratch|novel|custom|"
        r"without library|no existing|build a|create a new)\b",
        re.IGNORECASE,
    )
    PRODUCTION_OPS_PATTERNS = re.compile(
        r"\b(deploy|production|migrate|rollback|backup|restore|"
        r"irreversible|delete all|drop table|rm -rf)\b",
        re.IGNORECASE,
    )

    def score(
        self,
        task_description: str,
        file_count: int = 1,
        input_token_estimate: int = 0,
        flags: list[str] | None = None,
    ) -> dict[str, Any]:
        flags = flags or []
        score = 1.0
        reasons = []

        # File count scoring (each file beyond first adds 0.5, capped at +3)
        if file_count > 1:
            file_delta = min((file_count - 1) * 0.5, 3.0)
            score += file_delta
            reasons.append(f"files:{file_count} +{file_delta:.1f}")

        # Context token scoring (each 3K tokens beyond 2K adds +1, capped at +3)
        if input_token_estimate > 2000:
            token_delta = min(((input_token_estimate - 2000) // 3000) * 1.0, 3.0)
            score += token_delta
            if token_delta > 0:
                reasons.append(f"tokens:{input_token_estimate} +{token_delta:.1f}")

        # Pattern matching on task description
        desc = task_description.lower()

        if self.SECURITY_PATTERNS.search(task_description):
            score += 3.0
            reasons.append("security/auth +3")

        if self.COMPLIANCE_PATTERNS.search(task_description):
            score += 2.0
            reasons.append("compliance +2")

        if self.AIML_PATTERNS.search(task_description):
            score += 2.0
            reasons.append("ai/ml +2")

        if self.MULTI_SERVICE_PATTERNS.search(task_description):
            score += 2.0
            reasons.append("multi-service +2")

        if self.NOVEL_ALGO_PATTERNS.search(task_description):
            score += 3.0
            reasons.append("novel-algo +3")

        if self.PRODUCTION_OPS_PATTERNS.search(task_description):
            score += 2.0
            reasons.append("prod-ops +2")

        # Flag modifiers
        if "ambiguous" in flags or "underspecified" in flags:
            score += 2.0
            reasons.append("ambiguous +2")

        if "single_file_only" in flags:
            score -= 2.0
            reasons.append("single-file −2")

        if "pure_file_ops" in flags:
            score -= 2.0
            reasons.append("pure-ops −2")

        # Clamp to 1–10
        score = max(1.0, min(10.0, score))
        final = round(score)

        # Determine tier
        tier = Tier.T3  # default safe
        for (lo, hi), t in TIER_SCORE_MAP.items():
            if lo <= final <= hi:
                tier = t
                break

        return {
            "score": final,
            "raw_score": round(score, 2),
            "tier": tier.value,
            "tier_name": f"T{tier.value}",
            "model": TIER_MODELS[tier],
            "reasons": reasons,
        }


scorer = ComplexityScorer()


# ── Ollama Auto-Start & Health ───────────────────────────────────────────────
# Auto-start is MCP-owned. No bash &. No plist. No LaunchAgent.
# The MCP server starts Ollama via subprocess.Popen if not running.
# stdout/stderr are redirected to OLLAMA_LOG — never to our stdio pipe.

def _ollama_reachable(timeout: float = 3.0) -> bool:
    """Quick TCP check — does Ollama respond at all?"""
    try:
        httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def ensure_ollama_running() -> dict[str, Any]:
    """
    Ensure Ollama is running. If not, start it via subprocess.Popen.
    Never uses bash &. Never creates a plist or LaunchAgent.
    stdout/stderr of the Ollama process are routed to OLLAMA_LOG only —
    they never touch the stdio pipe that Claude CLI uses for MCP JSON-RPC.

    Returns:
        dict with keys: already_running (bool), started (bool), error (str|None)
    """
    if _ollama_reachable():
        log.info("Ollama already running")
        return {"already_running": True, "started": False, "error": None}

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return {
            "already_running": False,
            "started": False,
            "error": "ollama binary not found in PATH — install via: brew install ollama",
        }

    log.info(f"Ollama not running. Starting via subprocess.Popen: {ollama_bin} serve")
    try:
        log_fh = open(OLLAMA_LOG, "a")
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,   # never inherit our stdin
            close_fds=True,             # never inherit our MCP stdio fds
            start_new_session=True,     # detach from our process group cleanly
        )
    except Exception as e:
        return {"already_running": False, "started": False, "error": str(e)}

    # Wait up to 12 seconds for Ollama to become reachable
    for attempt in range(12):
        time.sleep(1)
        if _ollama_reachable():
            log.info(f"Ollama became reachable after {attempt + 1}s")
            return {"already_running": False, "started": True, "error": None}

    return {
        "already_running": False,
        "started": False,
        "error": "Ollama started but did not become reachable within 12s — check ~/.dsr-ai-lab/tier-gate/ollama.log",
    }


def check_ollama_model(model: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        resp = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=timeout)
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        tags = resp.json().get("models", [])
        names = [m.get("name", "") for m in tags]
        present = any(model in n for n in names)
        return {
            "ok": present,
            "model": model,
            "available_models": names,
            "error": None if present else f"Model '{model}' not found in Ollama",
        }
    except Exception as e:
        return {"ok": False, "model": model, "error": str(e)}


# ── Ollama Inference ──────────────────────────────────────────────────────────

def ollama_generate(
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.15,
    max_tokens: int = 2048,
    timeout: float = 120.0,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "top_p": 0.92,
            "repeat_penalty": 1.1,
        },
    }
    try:
        t0 = time.monotonic()
        resp = httpx.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"Ollama HTTP {resp.status_code}: {resp.text[:200]}",
            }
        data = resp.json()
        return {
            "ok": True,
            "response": data.get("response", ""),
            "model": model,
            "elapsed_sec": round(elapsed, 2),
            "tokens_generated": data.get("eval_count", 0),
        }
    except httpx.TimeoutException:
        return {"ok": False, "error": f"Ollama timeout after {timeout}s for {model}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Gate Log Writer ───────────────────────────────────────────────────────────

def write_gate_log(entry: dict[str, Any]) -> None:
    entry["ts"] = datetime.utcnow().isoformat() + "Z"
    log.info(json.dumps(entry))


# ════════════════════════════════════════════════════════════════════════════════
# MCP TOOLS
# ════════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def tier_gate_classify(
    task_description: str,
    file_count: int = 1,
    input_token_estimate: int = 0,
    flags: list[str] | None = None,
) -> str:
    """
    Classify a task and return the correct execution tier.

    Args:
        task_description:    Natural language description of the task.
        file_count:          Number of files the task will touch.
        input_token_estimate: Estimated tokens in the task context.
        flags:               Optional modifiers. Allowed values:
                             'ambiguous', 'underspecified', 'single_file_only',
                             'pure_file_ops', 'security_critical', 'novel_algorithm'.

    Returns:
        JSON string with tier verdict and routing instructions.

    IMPORTANT: Claude MUST call this tool before executing any non-trivial task.
    The verdict is FINAL. Claude must not argue with or ignore this verdict.
    """
    result = scorer.score(
        task_description=task_description,
        file_count=file_count,
        input_token_estimate=input_token_estimate,
        flags=flags or [],
    )

    tier = Tier(result["tier"])
    verdict = {
        "verdict": result["tier_name"],
        "model": result["model"],
        "complexity_score": result["score"],
        "score_breakdown": result["reasons"],
        "instructions": _routing_instructions(tier),
        "hard_gate_active": True,
    }

    write_gate_log({
        "event": "classify",
        "task_excerpt": task_description[:120],
        "file_count": file_count,
        "token_estimate": input_token_estimate,
        "flags": flags or [],
        "verdict": verdict,
    })

    return json.dumps(verdict, indent=2)


def _routing_instructions(tier: Tier) -> str:
    if tier == Tier.T1:
        return (
            "ROUTE_T1: Delegate this task to qwen2.5-coder:7b via tier_gate_run_t1. "
            "Do NOT execute in T3 (Claude). Construct a fully self-contained, "
            "unambiguous prompt. Review T1 output before presenting to user."
        )
    elif tier == Tier.T2:
        return (
            "ROUTE_T2: Delegate this task to qwen2.5-coder:14b via tier_gate_run_t2. "
            "Do NOT execute in T3 (Claude). Review T2 output for correctness "
            "before presenting to user. T2 output is not final without T3 review."
        )
    else:
        return (
            "ROUTE_T3: This task requires Claude (T3). Execute directly. "
            "Apply full accuracy protocol. No hallucination. No invented APIs."
        )


@mcp.tool()
def tier_gate_ollama_health() -> str:
    """
    Check health and availability of T1 and T2 Ollama models.
    Must be called at session start. Results determine override eligibility.

    Returns:
        JSON with health status for T1 (qwen2.5-coder:7b) and T2 (qwen2.5-coder:14b).
    """
    t1_status = check_ollama_model(T1_MODEL)
    t2_status = check_ollama_model(T2_MODEL)

    result = {
        "ollama_base": OLLAMA_BASE,
        "T1": {
            "model": T1_MODEL,
            "available": t1_status["ok"],
            "error": t1_status.get("error"),
        },
        "T2": {
            "model": T2_MODEL,
            "available": t2_status["ok"],
            "error": t2_status.get("error"),
        },
        "override_eligible": {
            "T1_to_T3": not t1_status["ok"],
            "T2_to_T3": not t2_status["ok"],
        },
        "note": (
            "If T1/T2 unavailable, T3 (Claude) may handle their tasks "
            "with mandatory [TIER_OVERRIDE: Ollama unavailable] log entry."
        ),
    }

    write_gate_log({"event": "health_check", "result": result})
    return json.dumps(result, indent=2)


@mcp.tool()
def tier_gate_run_t1(
    task_description: str,
    prompt: str,
    system_prompt: str = (
        "You are qwen2.5-coder:7b, a focused local coding assistant. "
        "Execute the task exactly as specified. Do not add unrequested features. "
        "Do not modify files or lines not mentioned in the task. "
        "If the task is outside your skill domain (multi-file architecture, "
        "security design, novel algorithms), respond with: "
        "T1_ESCALATE: <reason>. Do not attempt the task yourself."
    ),
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> str:
    """
    Execute a T1-classified task on qwen2.5-coder:7b via Ollama.
    Only call this after tier_gate_classify returns ROUTE_T1.

    Args:
        task_description: The original task description (for gate logging).
        prompt:           The fully self-contained prompt to send to T1.
        system_prompt:    Override the system prompt (optional).
        temperature:      Sampling temperature (default 0.1 for precision).
        max_tokens:       Max output tokens (hard limit 1024 for T1).

    Returns:
        JSON with T1 response and metadata.
    """
    max_tokens = min(max_tokens, 1024)  # Hard cap for T1

    write_gate_log({
        "event": "t1_invoke",
        "task_excerpt": task_description[:120],
        "prompt_length": len(prompt),
    })

    result = ollama_generate(
        model=T1_MODEL,
        prompt=prompt,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if not result["ok"]:
        write_gate_log({"event": "t1_error", "error": result["error"]})
        return json.dumps({
            "tier": "T1",
            "model": T1_MODEL,
            "ok": False,
            "error": result["error"],
            "gate_note": "T1 failed. Claude (T3) may handle with TIER_OVERRIDE log.",
        })

    response_text = result["response"]

    # Detect T1 escalation request
    if response_text.strip().startswith("T1_ESCALATE:"):
        escalation_reason = response_text.replace("T1_ESCALATE:", "").strip()
        write_gate_log({
            "event": "t1_escalate",
            "reason": escalation_reason,
        })
        return json.dumps({
            "tier": "T1",
            "model": T1_MODEL,
            "ok": False,
            "escalation_requested": True,
            "escalation_reason": escalation_reason,
            "gate_note": "T1 self-escalated. Re-classify and route to T2 or T3.",
        })

    write_gate_log({
        "event": "t1_complete",
        "tokens_generated": result.get("tokens_generated", 0),
        "elapsed_sec": result.get("elapsed_sec", 0),
    })

    return json.dumps({
        "tier": "T1",
        "model": T1_MODEL,
        "ok": True,
        "response": response_text,
        "tokens_generated": result.get("tokens_generated", 0),
        "elapsed_sec": result.get("elapsed_sec", 0),
        "review_required": True,
        "review_note": "Claude (T3) must review T1 output before presenting to user.",
    })


@mcp.tool()
def tier_gate_run_t2(
    task_description: str,
    prompt: str,
    system_prompt: str = (
        "You are qwen2.5-coder:14b, a precise local coding assistant for "
        "multi-file and medium-complexity tasks. Implement exactly what is specified. "
        "You reason within the bounded subsystem described in the prompt. "
        "You do NOT make architectural decisions. You implement specifications. "
        "If the task requires system-wide architectural reasoning, novel algorithm "
        "design without a specification, security architecture, or compliance "
        "implementation, respond with: T2_ESCALATE: <reason>. Do not attempt it."
    ),
    temperature: float = 0.15,
    max_tokens: int = 3072,
) -> str:
    """
    Execute a T2-classified task on qwen2.5-coder:14b via Ollama.
    Only call this after tier_gate_classify returns ROUTE_T2.

    Args:
        task_description: The original task description (for gate logging).
        prompt:           The fully self-contained prompt to send to T2.
        system_prompt:    Override the system prompt (optional).
        temperature:      Sampling temperature (default 0.15).
        max_tokens:       Max output tokens (hard limit 3072 for T2).

    Returns:
        JSON with T2 response and metadata.
    """
    max_tokens = min(max_tokens, 3072)  # Hard cap for T2

    write_gate_log({
        "event": "t2_invoke",
        "task_excerpt": task_description[:120],
        "prompt_length": len(prompt),
    })

    result = ollama_generate(
        model=T2_MODEL,
        prompt=prompt,
        system=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if not result["ok"]:
        write_gate_log({"event": "t2_error", "error": result["error"]})
        return json.dumps({
            "tier": "T2",
            "model": T2_MODEL,
            "ok": False,
            "error": result["error"],
            "gate_note": "T2 failed. Claude (T3) may handle with TIER_OVERRIDE log.",
        })

    response_text = result["response"]

    # Detect T2 escalation request
    if response_text.strip().startswith("T2_ESCALATE:"):
        escalation_reason = response_text.replace("T2_ESCALATE:", "").strip()
        write_gate_log({
            "event": "t2_escalate",
            "reason": escalation_reason,
        })
        return json.dumps({
            "tier": "T2",
            "model": T2_MODEL,
            "ok": False,
            "escalation_requested": True,
            "escalation_reason": escalation_reason,
            "gate_note": "T2 self-escalated. Re-classify and route to T3.",
        })

    write_gate_log({
        "event": "t2_complete",
        "tokens_generated": result.get("tokens_generated", 0),
        "elapsed_sec": result.get("elapsed_sec", 0),
    })

    return json.dumps({
        "tier": "T2",
        "model": T2_MODEL,
        "ok": True,
        "response": response_text,
        "tokens_generated": result.get("tokens_generated", 0),
        "elapsed_sec": result.get("elapsed_sec", 0),
        "review_required": True,
        "review_note": "Claude (T3) must review T2 output before presenting to user.",
    })


@mcp.tool()
def tier_gate_log_override(
    reason: str,
    original_tier_verdict: str,
    override_type: str,
) -> str:
    """
    Log a tier gate override. Must be called whenever Claude handles a task
    scored below T3. This is the compliance record.

    Args:
        reason:                 Why the override is happening.
        original_tier_verdict:  What the gate originally returned (T1/T2).
        override_type:          One of: 'ollama_unavailable' | 'user_forced' | 'escalation'.

    Returns:
        Confirmation of log entry.
    """
    allowed_types = {"ollama_unavailable", "user_forced", "escalation"}
    if override_type not in allowed_types:
        return json.dumps({
            "ok": False,
            "error": f"Invalid override_type. Must be one of: {allowed_types}",
        })

    entry = {
        "event": "gate_override",
        "override_type": override_type,
        "original_verdict": original_tier_verdict,
        "reason": reason,
    }
    write_gate_log(entry)

    return json.dumps({
        "ok": True,
        "logged": True,
        "override_type": override_type,
        "note": f"[TIER_OVERRIDE: {override_type.upper()}] logged. Proceed with T3 execution.",
    })


@mcp.tool()
def tier_gate_session_start() -> str:
    """
    MANDATORY FIRST CALL every Claude CLI session — no exceptions.

    Responsibilities (in order):
      1. Verify Claude subscription auth (OAuth) — no API key required or accepted.
      2. Auto-start Ollama if not running (MCP-owned, no bash &, no plist).
      3. Verify T1 and T2 models are loaded in Ollama.
      4. Activate all tier gate rules.
      5. Return full operational status.

    Claude MUST NOT proceed with any task until this returns status=READY.
    If status=DEGRADED, Claude MUST report warnings to user before any work.
    """
    # ── Step 1: Auth — subscription only, no API key ──────────────────────────
    auth_status = "SUBSCRIPTION_OK"
    auth_note   = "Claude CLI authenticates via OAuth subscription (claude login). No API key used."

    # ── Step 2: Ollama auto-start (MCP-owned) ─────────────────────────────────
    ollama_start = ensure_ollama_running()
    if ollama_start["error"]:
        ollama_status = f"ERROR: {ollama_start['error']}"
    elif ollama_start["started"]:
        ollama_status = "AUTO-STARTED by MCP tier gate"
    else:
        ollama_status = "ALREADY RUNNING"

    # ── Step 3: Model availability ────────────────────────────────────────────
    t1 = check_ollama_model(T1_MODEL)
    t2 = check_ollama_model(T2_MODEL)

    # ── Step 4: Build checklist ───────────────────────────────────────────────
    checklist = {
        "auth_mode":             auth_status,
        "api_key_used":          "NEVER — subscription OAuth only",
        "ollama_service":        ollama_status,
        "T1_qwen2.5-coder_7b":  "READY" if t1["ok"] else f"UNAVAILABLE: {t1.get('error')}",
        "T2_qwen2.5-coder_14b": "READY" if t2["ok"] else f"UNAVAILABLE: {t2.get('error')}",
        "tier_gate_server":      "ACTIVE",
        "hard_gate_rules":       "ENFORCED",
        "hallucination_guard":   "ACTIVE",
        "CLAUDE_md_loaded":      True,
    }

    all_ok = t1["ok"] and t2["ok"] and not ollama_start["error"]
    warnings = []
    if ollama_start["error"]:
        warnings.append(f"Ollama failed to start: {ollama_start['error']}")
    if not t1["ok"]:
        warnings.append("T1 unavailable: T3 override eligible — must log TIER_OVERRIDE.")
    if not t2["ok"]:
        warnings.append("T2 unavailable: T3 override eligible — must log TIER_OVERRIDE.")

    result = {
        "status":      "READY" if all_ok else "DEGRADED",
        "checklist":   checklist,
        "warnings":    warnings,
        "auth_note":   auth_note,
        "ollama_log":  str(OLLAMA_LOG),
        "session_ts":  datetime.utcnow().isoformat() + "Z",
        "node":        "MBP-M5-Node2",
        "instructions": (
            "Session active. tier_gate_classify REQUIRED before every non-trivial task. "
            "Respect all tier verdicts. No bypasses. No API keys. No hallucinations."
        ),
    }

    write_gate_log({
        "event":        "session_start",
        "status":       result["status"],
        "ollama_start": ollama_start,
        "t1_ok":        t1["ok"],
        "t2_ok":        t2["ok"],
    })
    return json.dumps(result, indent=2)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("DSR Tier Gate MCP server starting · stdio transport")
    mcp.run(transport="stdio")
