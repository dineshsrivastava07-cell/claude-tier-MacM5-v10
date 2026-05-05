#!/usr/bin/env python3
"""
startup_banner.py — SessionStart hook for Claude Tier System v10.1

Fires once per Claude session. Performs parallel liveness checks across:
  - Claude OAuth (macOS Keychain entry presence)
  - Ollama daemon
  - T1 / T2 / T-CLOUD primary / T-CLOUD fallback model registration
  - Audit DB
  - Hooks files
  - Skills registry

Then prewarms T2 (gemma4:26b) in the background so the first edit doesn't
incur a cold start. T1 stays cold; loads on-demand for score 1-3 tasks.

KEY MECHANICS:
  - T3 reuses T2's model — no separate check needed
  - T-CLOUD fallback (gemma4:31b-cloud) is a registration check only;
    Ollama Cloud models don't need pre-pull
  - 5-second total budget; never blocks session start

DEPENDENCIES: stdlib only.
VERSION: v10.1 (May 2026)
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

T1_MODEL = os.environ.get("T1_MODEL", "gemma4:e4b")
T2_MODEL = os.environ.get("T2_MODEL", "gemma4:26b")
T_CLOUD_PRIMARY = os.environ.get("T_CLOUD_PRIMARY", "qwen3-coder:480b-cloud")
T_CLOUD_FALLBACK = os.environ.get("T_CLOUD_FALLBACK", "gemma4:31b-cloud")

T2_KEEP_ALIVE = os.environ.get("T2_KEEP_ALIVE", "-1")

AUDIT_DB = Path(os.path.expanduser(
    os.environ.get("DSR_AI_LAB_AUDIT_DB", "~/.dsr-ai-lab/audit.db")
))
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
# Resolve skills file: env var first, then project dir, then ~/.claude fallback
SKILLS_FILE = Path(os.path.expanduser(
    os.environ.get(
        "SKILLS_PATH",
        os.environ.get("SKILLS_REGISTRY", str(PROJECT_DIR / "global-skills.json"))
    )
))
_SKILLS_FALLBACK = Path.home() / ".claude" / "global-skills.json"

CHECK_TIMEOUT = 2.0  # per check
TOTAL_BUDGET_SEC = 5.0


# ─────────────────────────────────────────────────────────────────────────
# Individual probes (each runs on a thread, must complete <2s)
# ─────────────────────────────────────────────────────────────────────────

def probe_claude_oauth() -> dict:
    """Check macOS Keychain for 'Claude Code-credentials' entry."""
    out = {"name": "Claude OAuth", "status": "unknown", "detail": ""}
    if shutil.which("security") is None:
        out["status"] = "skipped"
        out["detail"] = "not on macOS"
        return out
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials"],
            capture_output=True, text=True, timeout=2,
        )
        if proc.returncode == 0:
            out["status"] = "ok"
            out["detail"] = "Keychain entry found"
        else:
            out["status"] = "missing"
            out["detail"] = "Run: claude auth login"
    except Exception as e:
        out["status"] = "error"
        out["detail"] = str(e)
    return out


def probe_ollama() -> dict:
    out = {"name": "Ollama daemon", "status": "unknown", "detail": ""}
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=CHECK_TIMEOUT) as r:
            tags = json.loads(r.read().decode())
        out["status"] = "ok"
        out["detail"] = f"{len(tags.get('models', []))} models pulled"
        out["_pulled"] = {m.get("name", "") for m in tags.get("models", [])}
    except Exception as e:
        out["status"] = "down"
        out["detail"] = f"unreachable at {OLLAMA_HOST} ({type(e).__name__})"
        out["_pulled"] = set()
    return out


def probe_audit_db() -> dict:
    out = {"name": "Audit DB", "status": "unknown", "detail": ""}
    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    if not AUDIT_DB.exists():
        out["status"] = "new"
        out["detail"] = f"will be created at {AUDIT_DB}"
        return out
    try:
        conn = sqlite3.connect(str(AUDIT_DB), timeout=CHECK_TIMEOUT)
        n = conn.execute("SELECT COUNT(*) FROM routing_log").fetchone()[0]
        conn.close()
        out["status"] = "ok"
        out["detail"] = f"{n} routing entries"
    except sqlite3.OperationalError:
        out["status"] = "new"
        out["detail"] = "schema will be initialized on first route"
    except Exception as e:
        out["status"] = "error"
        out["detail"] = str(e)
    return out


def probe_skills() -> dict:
    out = {"name": "Skills registry", "status": "unknown", "detail": ""}
    path = SKILLS_FILE if SKILLS_FILE.exists() else _SKILLS_FALLBACK
    if not path.exists():
        out["status"] = "missing"
        out["detail"] = f"not found at {SKILLS_FILE}"
        return out
    try:
        data = json.loads(path.read_text())
        n = len(data.get("skills", []))
        out["status"] = "ok"
        out["detail"] = f"{n} skill protocols  [{path}]"
    except Exception as e:
        out["status"] = "error"
        out["detail"] = str(e)
    return out


def probe_hooks() -> dict:
    out = {"name": "Hooks", "status": "unknown", "detail": ""}
    hooks_dir = Path(os.environ.get("DSR_HOOKS_DIR", str(PROJECT_DIR / "dsr-ai-lab" / "hooks")))
    expected = ["intercept.py", "bash_safety.py", "startup_banner.py"]
    missing = [h for h in expected if not (hooks_dir / h).exists()]
    if missing:
        out["status"] = "missing"
        out["detail"] = f"absent: {', '.join(missing)}"
    else:
        out["status"] = "ok"
        out["detail"] = f"{len(expected)} hooks present"
    return out


def warm_t2_background() -> None:
    """Fire-and-forget T2 prewarm via /api/chat (supports keep_alive)."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps({
                "model": T2_MODEL,
                "messages": [{"role": "user", "content": "ready"}],
                "stream": False,
                "keep_alive": T2_KEEP_ALIVE,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=120.0).read()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────

def run_probes() -> tuple[list[dict], dict]:
    """Run all probes in parallel within the budget. Returns (results, ollama_probe)."""
    threads = []
    results: dict[str, dict] = {}
    ollama_result: dict = {}

    def runner(probe_fn, key):
        try:
            results[key] = probe_fn()
        except Exception as e:
            results[key] = {"name": key, "status": "error", "detail": str(e)}

    probes = [
        (probe_claude_oauth, "oauth"),
        (probe_ollama, "ollama"),
        (probe_audit_db, "audit"),
        (probe_skills, "skills"),
        (probe_hooks, "hooks"),
    ]
    for fn, key in probes:
        t = threading.Thread(target=runner, args=(fn, key), daemon=True)
        t.start()
        threads.append(t)

    deadline = time.time() + TOTAL_BUDGET_SEC
    for t in threads:
        remaining = deadline - time.time()
        if remaining > 0:
            t.join(timeout=remaining)

    if "ollama" in results:
        ollama_result = results["ollama"]

    pulled = ollama_result.get("_pulled", set())

    # Model-presence checks (require Ollama up)
    ordered = [
        results.get("oauth", {"name": "Claude OAuth", "status": "timeout", "detail": ""}),
        results.get("ollama", {"name": "Ollama daemon", "status": "timeout", "detail": ""}),
    ]

    if ollama_result.get("status") == "ok":
        # Local models — must be pulled
        for label, model in (
            ("T1 model", T1_MODEL),
            ("T2 model", T2_MODEL),
        ):
            is_pulled = any(name.startswith(model) for name in pulled)
            ordered.append({
                "name": label,
                "status": "ok" if is_pulled else "missing",
                "detail": model + ("" if is_pulled else f"  (run: ollama pull {model})"),
            })
        # Cloud models — streamed from Ollama Cloud, never pulled locally
        for label, model in (
            ("T-CLOUD primary", T_CLOUD_PRIMARY),
            ("T-CLOUD fallback", T_CLOUD_FALLBACK),
        ):
            is_cloud = model.endswith("-cloud")
            ordered.append({
                "name": label,
                "status": "ok" if is_cloud else "missing",
                "detail": model + (" (cloud — always active)" if is_cloud else f"  (run: ollama pull {model})"),
            })
    else:
        ordered.append({
            "name": "Tier models",
            "status": "skipped",
            "detail": "Ollama unreachable — model checks deferred",
        })

    ordered.extend([
        results.get("audit", {"name": "Audit DB", "status": "timeout", "detail": ""}),
        results.get("hooks", {"name": "Hooks", "status": "timeout", "detail": ""}),
        results.get("skills", {"name": "Skills registry", "status": "timeout", "detail": ""}),
    ])

    return ordered, ollama_result


STATUS_GLYPHS = {
    "ok": "✓",
    "missing": "✗",
    "down": "✗",
    "error": "!",
    "timeout": "?",
    "new": "·",
    "skipped": "·",
    "unknown": "?",
}


def render_banner(rows: list[dict]) -> str:
    """Render rows as a fixed-width frame banner."""
    lines = [
        "╭──────────────────────────────────────────────────────────────────────╮",
        "│  Claude Tier System v10.1 · MBP M5 · Hard-Gate Hybrid                │",
        "│  Brain: Claude OAuth   Local: Gemma 4   Cloud: Qwen3 / Gemma 4       │",
        "├──────────────────────────────────────────────────────────────────────┤",
    ]
    for r in rows:
        glyph = STATUS_GLYPHS.get(r.get("status", "unknown"), "?")
        name = r.get("name", "")
        detail = r.get("detail", "")
        line = f"│  {glyph}  {name:<22} {detail}"
        # Pad to 70 chars (interior of the box)
        line = line[:71].ljust(71) + "│"
        lines.append(line)
    lines.append("╰──────────────────────────────────────────────────────────────────────╯")
    return "\n".join(lines)


def main() -> int:
    rows, ollama = run_probes()

    # Determine overall status
    has_critical_failure = any(
        r["status"] in ("missing", "down")
        and r["name"] in ("Ollama daemon", "T2 model", "Hooks")
        for r in rows
    )

    banner = render_banner(rows)

    if ollama.get("status") == "ok":
        # Check T2 is pulled before warming
        pulled = ollama.get("_pulled", set())
        if any(name.startswith(T2_MODEL) for name in pulled):
            threading.Thread(target=warm_t2_background, daemon=True).start()

    # Emit SessionStart hook output: banner via additionalContext
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Tier system status:\n\n```\n" + banner + "\n```\n\n"
                + ("⚠ DEGRADED — see warnings above. Some features may not work.\n"
                   if has_critical_failure else
                   "✓ All systems READY. T2 prewarming in background.\n")
                + "\nTier reference:\n"
                + "  Score 1-3 → T1 (gemma4:e4b, on-demand)\n"
                + "  Score 4-6 → T2 (gemma4:26b, always warm)\n"
                + "  Score 7-8 → T3 (gemma4:26b + <|think|> token, no extra RAM)\n"
                + "  Score 9-10 → T-CLOUD (qwen3-coder:480b-cloud → gemma4:31b-cloud)\n"
            )
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Never block session start on hook errors
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"Startup banner failed: {type(e).__name__}: {e}\n"
            }
        }))
        sys.exit(0)
