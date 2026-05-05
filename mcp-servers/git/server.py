#!/usr/bin/env python3
"""
DSR AI-Lab · Git MCP Server
All git operations for Claude CLI / Code / Desktop / Cowork.
No API key. Subscription OAuth only. FastMCP stdio.
"""
import json, subprocess, sys
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("dsr-git")

def _run(cmd: list[str], cwd: str | None = None) -> dict:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "stdout": r.stdout.strip(),
                "stderr": r.stderr.strip(), "code": r.returncode}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}

def _repo(path: str) -> str:
    """Resolve repo root from any path inside a git repo."""
    r = _run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    return r["stdout"] if r["ok"] else path

@mcp.tool()
def git_status(repo_path: str) -> str:
    """Full git status including untracked, staged, modified."""
    root = _repo(repo_path)
    r = _run(["git", "status", "--porcelain", "-b"], cwd=root)
    verbose = _run(["git", "status"], cwd=root)
    return json.dumps({"root": root, "porcelain": r["stdout"],
                       "verbose": verbose["stdout"], "ok": r["ok"]})

@mcp.tool()
def git_diff(repo_path: str, staged: bool = False, file_path: str = "") -> str:
    """Show diff. staged=True for index diff. file_path to scope to one file."""
    root = _repo(repo_path)
    cmd = ["git", "diff"]
    if staged: cmd.append("--staged")
    if file_path: cmd.append(file_path)
    r = _run(cmd, cwd=root)
    stat = _run(cmd + ["--stat"], cwd=root)
    return json.dumps({"diff": r["stdout"], "stat": stat["stdout"], "ok": r["ok"]})

@mcp.tool()
def git_log(repo_path: str, n: int = 20, oneline: bool = True, author: str = "") -> str:
    """Commit log. n=count, oneline=compact, author filter."""
    root = _repo(repo_path)
    cmd = ["git", "log", f"-{n}", "--format=%H|%an|%ai|%s"]
    if oneline: cmd = ["git", "log", f"-{n}", "--oneline"]
    if author: cmd += [f"--author={author}"]
    r = _run(cmd, cwd=root)
    return json.dumps({"log": r["stdout"], "ok": r["ok"]})

@mcp.tool()
def git_branch(repo_path: str, action: str = "list", name: str = "", base: str = "") -> str:
    """Branch ops. action: list|create|delete|checkout|current."""
    root = _repo(repo_path)
    cmds = {
        "list":     ["git", "branch", "-a", "-v"],
        "current":  ["git", "branch", "--show-current"],
        "create":   ["git", "checkout", "-b", name] + ([base] if base else []),
        "delete":   ["git", "branch", "-d", name],
        "checkout": ["git", "checkout", name],
    }
    if action not in cmds:
        return json.dumps({"ok": False, "error": f"Unknown action: {action}"})
    r = _run(cmds[action], cwd=root)
    return json.dumps({"action": action, "output": r["stdout"],
                       "error": r["stderr"], "ok": r["ok"]})

@mcp.tool()
def git_add(repo_path: str, paths: list[str] | None = None, all: bool = False) -> str:
    """Stage files. paths=specific files, all=True for -A."""
    root = _repo(repo_path)
    cmd = ["git", "add", "-A"] if all else ["git", "add"] + (paths or ["."])
    r = _run(cmd, cwd=root)
    status = _run(["git", "status", "--short"], cwd=root)
    return json.dumps({"staged": status["stdout"], "ok": r["ok"], "error": r["stderr"]})

@mcp.tool()
def git_commit(repo_path: str, message: str, body: str = "") -> str:
    """Commit staged changes. message=subject line, body=optional detail."""
    root = _repo(repo_path)
    full_msg = f"{message}\n\n{body}".strip() if body else message
    r = _run(["git", "commit", "-m", full_msg], cwd=root)
    if r["ok"]:
        last = _run(["git", "log", "-1", "--oneline"], cwd=root)
        return json.dumps({"ok": True, "commit": last["stdout"]})
    return json.dumps({"ok": False, "error": r["stderr"],
                       "hint": "Nothing staged? Run git_add first."})

@mcp.tool()
def git_push(repo_path: str, remote: str = "origin", branch: str = "") -> str:
    """Push to remote. Requires explicit call — never auto-pushes."""
    root = _repo(repo_path)
    if not branch:
        branch = _run(["git", "branch", "--show-current"], cwd=root)["stdout"]
    r = _run(["git", "push", remote, branch], cwd=root)
    return json.dumps({"ok": r["ok"], "output": r["stdout"] or r["stderr"],
                       "pushed_to": f"{remote}/{branch}"})

@mcp.tool()
def git_pull(repo_path: str, remote: str = "origin", branch: str = "") -> str:
    """Pull from remote with rebase."""
    root = _repo(repo_path)
    cmd = ["git", "pull", "--rebase", remote]
    if branch: cmd.append(branch)
    r = _run(cmd, cwd=root)
    return json.dumps({"ok": r["ok"], "output": r["stdout"] or r["stderr"]})

@mcp.tool()
def git_stash(repo_path: str, action: str = "push", message: str = "") -> str:
    """Stash ops. action: push|pop|list|drop."""
    root = _repo(repo_path)
    cmds = {
        "push": ["git", "stash", "push", "-m", message or "dsr-stash"],
        "pop":  ["git", "stash", "pop"],
        "list": ["git", "stash", "list"],
        "drop": ["git", "stash", "drop"],
    }
    r = _run(cmds.get(action, ["git", "stash", "list"]), cwd=root)
    return json.dumps({"action": action, "output": r["stdout"], "ok": r["ok"]})

@mcp.tool()
def git_show(repo_path: str, ref: str = "HEAD") -> str:
    """Show commit detail for ref (hash, HEAD, branch name)."""
    root = _repo(repo_path)
    r = _run(["git", "show", "--stat", ref], cwd=root)
    return json.dumps({"ref": ref, "detail": r["stdout"], "ok": r["ok"]})

@mcp.tool()
def git_blame(repo_path: str, file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Blame a file. Optionally scope to line range."""
    root = _repo(repo_path)
    cmd = ["git", "blame", "--line-porcelain"]
    if end_line > 0: cmd += [f"-L{start_line},{end_line}"]
    cmd.append(file_path)
    r = _run(cmd, cwd=root)
    return json.dumps({"blame": r["stdout"][:8000], "ok": r["ok"]})

if __name__ == "__main__":
    mcp.run(transport="stdio")
