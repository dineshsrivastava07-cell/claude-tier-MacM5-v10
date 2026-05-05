#!/usr/bin/env python3
"""
bash_safety.py — PreToolUse hook for the Bash tool

Prevents Brain (Claude) from bypassing the Edit/Write hard gate via Bash
redirection. Without this, a determined Brain could execute:

    bash -c 'cat > foo.py << EOF ... EOF'
    echo "contents" > bar.py
    cp /tmp/generated.py /project/src/file.py

...and write code files without going through the local-executor gate.
That defeats the entire architecture. This hook detects such patterns
and blocks them with exit 2 + a stderr message instructing Brain to use
the proper Edit/Write tool path instead.

INPUT (stdin, JSON):
  {
    "session_id": "...",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "..."},
    ...
  }

OUTPUT:
  - Exit 0 with no stdout: allow the bash command (default)
  - Exit 2 with stderr message: block the command, message fed back to Brain

VERSION: v10.1 (May 2026)
"""

import json
import os
import re
import sys
import logging
from pathlib import Path


LOG_DIR = Path(os.path.expanduser(os.environ.get("DSR_AI_LAB_LOG_DIR", "~/.dsr-ai-lab/logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "bash_safety.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("bash_safety")


# Code file extensions whose creation/modification must go through the Edit gate
CODE_EXTENSIONS = (
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "go", "rs", "rb", "java",
    "kt", "kts", "swift", "c", "h", "cpp", "cxx", "hpp", "cs", "php",
    "yaml", "yml", "json", "toml", "html", "css", "scss", "vue", "svelte",
    "sh", "bash", "zsh", "sql", "graphql", "proto", "ipynb",
    "tf", "hcl", "dockerfile", "makefile", "lock", "env",
)

# Compiled patterns
EXT_GROUP = "|".join(re.escape(e) for e in CODE_EXTENSIONS)

PATTERNS = {
    # Output redirection to a code file
    "redirect_overwrite": re.compile(
        rf"(?:^|[\s;&|`(])(?:[^|]+?)\s*>\s*\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    "redirect_append": re.compile(
        rf"(?:^|[\s;&|`(])(?:[^|]+?)\s*>>\s*\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    # tee writing to a code file
    "tee_to_code": re.compile(
        rf"\btee\s+(?:-[a-z]+\s+)*\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    # cp / mv into a path that looks like project source
    "cp_to_code": re.compile(
        rf"\bcp\s+(?:-[a-z]+\s+)*\S+\s+\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    "mv_to_code": re.compile(
        rf"\bmv\s+(?:-[a-z]+\s+)*\S+\s+\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    # heredoc to a code file: cat > foo.py <<EOF
    "heredoc_to_code": re.compile(
        rf"\bcat\s*>\s*\S*\.({EXT_GROUP})\b\s*<<",
        re.IGNORECASE,
    ),
    # alternate heredoc ordering: cat <<EOF > foo.py  (or  <<-EOF, <<'EOF', etc.)
    "heredoc_to_code_reversed": re.compile(
        rf"<<-?\s*['\"]?\w*['\"]?[\s\S]*?>\s*\S*\.({EXT_GROUP})\b",
        re.IGNORECASE,
    ),
    # sed -i in place edit (modifies code without going through Edit)
    "sed_inplace": re.compile(
        rf"\bsed\s+(?:-[a-z]*\s+)*-i\b",
        re.IGNORECASE,
    ),
    # python heredoc writing files: python -c "open('x.py','w')..."
    "python_open_write": re.compile(
        r"\bopen\s*\(\s*['\"][^'\"]+['\"]\s*,\s*['\"][wa]\b",
        re.IGNORECASE,
    ),
}

# Dangerous patterns we always block regardless of redirect logic
HARD_BLOCK = {
    "rm_rf_root": re.compile(r"\brm\s+(?:-[a-z]+\s+)*-rf?\s+/(?:\s|$)"),
    "rm_rf_home": re.compile(r"\brm\s+(?:-[a-z]+\s+)*-rf?\s+(?:~|\$HOME)\b"),
    "launchctl": re.compile(r"\blaunchctl\b"),
    "plist_write": re.compile(r"\.plist\b.*[>]"),
    "sudo": re.compile(r"\bsudo\b"),
    "anthropic_key_export": re.compile(
        r"\bexport\s+ANTHROPIC_API_KEY\b",
        re.IGNORECASE,
    ),
}


def block(reason: str, suggestion: str = "") -> int:
    """Emit blocking message to stderr and exit 2."""
    msg = f"[bash_safety] BLOCKED: {reason}"
    if suggestion:
        msg += f"\nSuggestion: {suggestion}"
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
    log.warning(f"Blocked: {reason}")
    return 2


def allow() -> int:
    return 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        log.error(f"Bad JSON on stdin: {e}")
        return allow()  # don't block on hook errors

    tool_input = event.get("tool_input", {}) or {}
    command = tool_input.get("command", "")

    if not command:
        return allow()

    # Hard-block patterns first
    for name, pat in HARD_BLOCK.items():
        if pat.search(command):
            return block(
                f"Bash command matches hard-block rule '{name}': {pat.pattern}",
                {
                    "rm_rf_root": "Never run rm -rf on / or system directories.",
                    "rm_rf_home": "Never run rm -rf on $HOME. Be specific.",
                    "launchctl": "Constitution forbids launchd / launchctl. Manage Ollama via Ollama.app GUI.",
                    "plist_write": "Constitution forbids .plist creation. Persistent daemons are not allowed.",
                    "sudo": "Sudo not permitted. Use user-level operations.",
                    "anthropic_key_export": "Constitution forbids ANTHROPIC_API_KEY. Authentication is OAuth-only via macOS Keychain.",
                }.get(name, "See CLAUDE.md v3.0 for the constitution."),
            )

    # Gate-bypass patterns
    for name, pat in PATTERNS.items():
        m = pat.search(command)
        if m:
            return block(
                f"Bash command writes to a code file ('{name}' pattern matched: {m.group(0).strip()}). "
                f"This bypasses the Edit/Write hard gate which routes to local Gemma executors.",
                "Use the Edit, Write, or MultiEdit tool instead. The PreToolUse hook will route the "
                "actual content generation to a local Gemma model via tier-enforcer-mcp. "
                "If you genuinely need to run this Bash command (e.g., for a tool config that isn't code), "
                "tell the user explicitly and ask them to override.",
            )

    return allow()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log.exception("Unhandled exception in bash_safety hook")
        # Never block on hook errors — the gate has hooks of its own
        sys.exit(0)
