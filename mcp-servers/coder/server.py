#!/usr/bin/env python3
"""
DSR AI-Lab · Coder MCP Server
Programming, complex coding, multi-file edit, cross-file edit orchestration.
FastMCP stdio. No API key. Subscription OAuth only.
"""
import json, re
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("dsr-coder")

LOG_PATH = Path.home() / ".dsr-ai-lab" / "coder" / "coder.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def _log(entry: dict) -> None:
    entry["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ── Code Review ───────────────────────────────────────────────────────────────

@mcp.tool()
def code_review_checklist(
    language: str,
    file_path: str,
    review_focus: str = "general",
) -> str:
    """
    Return a language-specific code review checklist Claude must execute on a file.
    review_focus: general|security|performance|api|db|async

    Claude reads the file FIRST, then applies every checklist item.
    """
    base_checks = [
        "All functions/methods have docstrings or type annotations",
        "No unused imports or dead code",
        "Error handling: no bare except, errors are logged not swallowed",
        "No hardcoded secrets, URLs, or magic numbers",
        "Input validation at all public entry points",
        "Consistent naming conventions throughout",
        "No TODO/FIXME left uncommitted unless intentional",
    ]
    lang_checks = {
        "python": [
            "Type hints on all function signatures",
            "f-strings used (not % or .format) for consistency",
            "Context managers used for file/db/network resources",
            "No mutable default arguments",
            "Pydantic or dataclasses for data models, not raw dicts",
            "__all__ defined in modules with public API",
        ],
        "typescript": [
            "No 'any' types — strict TypeScript enforced",
            "Async functions always have error boundaries",
            "React hooks follow rules-of-hooks",
            "No console.log left in production paths",
            "Proper null/undefined handling with optional chaining",
        ],
        "javascript": [
            "let/const only — no var",
            "Promises not mixed with callbacks",
            "No console.log in production code",
            "Error boundaries around async code",
        ],
        "sql": [
            "All queries parameterised — no string interpolation",
            "Indices exist for all WHERE and JOIN columns",
            "EXPLAIN plan reviewed for expensive queries",
            "Transactions used where atomicity required",
        ],
    }
    focus_checks = {
        "security": ["SQL injection points", "XSS vectors", "Unvalidated redirects",
                     "Insecure deserialization", "Missing auth checks on endpoints"],
        "performance": ["N+1 queries in loops", "Missing caching on expensive ops",
                        "Unbounded list operations", "Sync I/O in async context"],
        "api": ["All endpoints return consistent error shapes", "Rate limiting present",
                "Auth middleware applied", "Request/response types documented"],
        "db": ["Transactions wrap multi-statement operations",
               "Connection pooling configured", "Indices match query patterns",
               "Migration scripts are reversible"],
        "async": ["No blocking calls inside async functions",
                  "Proper task cancellation handling",
                  "Deadlock prevention in concurrent sections"],
    }
    checks = base_checks + lang_checks.get(language.lower(), []) + focus_checks.get(review_focus, [])
    _log({"event": "code_review_checklist", "lang": language, "focus": review_focus})
    return json.dumps({
        "ok": True,
        "file": file_path,
        "language": language,
        "focus": review_focus,
        "checklist": checks,
        "output_format": {
            "findings": [{"check": "", "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
                          "line": 0, "issue": "", "fix": ""}],
            "verdict": "PASS|FAIL|NEEDS_WORK",
            "summary": "",
        },
        "instruction": f"Read {file_path} completely, then apply every checklist item. "
                       "Report findings with exact line numbers.",
    })

# ── Multi-File Edit Orchestration ─────────────────────────────────────────────

@mcp.tool()
def code_multi_file_plan(
    objective: str,
    files: list[str],
    change_type: str = "feature",
) -> str:
    """
    Plan a coordinated multi-file edit. Returns an ordered edit sequence
    that minimises conflicts and preserves consistency.

    change_type: feature|refactor|bugfix|migration|api_change

    Claude MUST follow this edit order exactly. Never edit files out of order.
    Never commit partial multi-file changes.
    """
    if not files:
        return json.dumps({"ok": False, "error": "No files provided"})

    # Classify files by role (heuristic)
    def _classify(f: str) -> str:
        fl = f.lower()
        if any(x in fl for x in ["test", "spec"]): return "test"
        if any(x in fl for x in ["model", "schema", "entity"]): return "model"
        if any(x in fl for x in ["route", "controller", "view", "handler"]): return "interface"
        if any(x in fl for x in ["service", "use_case", "domain"]): return "domain"
        if any(x in fl for x in ["repo", "repository", "db", "database"]): return "data"
        if any(x in fl for x in ["config", "setting", "env"]): return "config"
        if any(x in fl for x in ["migration"]): return "migration"
        return "other"

    classified = [{"file": f, "role": _classify(f)} for f in files]

    # Safe edit order: config → migration → model → data → domain → interface → test
    order_map = {"config": 0, "migration": 1, "model": 2, "data": 3,
                 "domain": 4, "interface": 5, "test": 6, "other": 4}
    ordered = sorted(classified, key=lambda x: order_map[x["role"]])

    edit_plan = []
    for i, item in enumerate(ordered):
        edit_plan.append({
            "step": i + 1,
            "file": item["file"],
            "role": item["role"],
            "pre_edit_action": f"Read {item['file']} completely and verify current state",
            "post_edit_action": "Read file again to confirm edit applied correctly",
            "verification": "Run syntax check and/or relevant tests",
            "blocking_next": i < len(ordered) - 1,
        })

    _log({"event": "multi_file_plan", "objective": objective[:80],
          "files": len(files), "change_type": change_type})
    return json.dumps({
        "ok": True,
        "objective": objective,
        "change_type": change_type,
        "total_files": len(files),
        "edit_plan": edit_plan,
        "hard_rules": [
            "Read file before every edit — no exceptions",
            "Read file after every edit to confirm correctness",
            "Do not proceed to next file if current file has errors",
            "Never edit test files before the code they test",
            "Run tests after all edits complete before declaring done",
            "Store progress in mem_short_store after each file",
        ],
    }, indent=2)

# ── Cross-File Dependency Analysis ────────────────────────────────────────────

@mcp.tool()
def code_cross_file_deps(
    root_path: str,
    entry_file: str,
    language: str = "python",
    max_depth: int = 4,
) -> str:
    """
    Analyse cross-file import/dependency chain from an entry point.
    Returns dependency graph Claude uses to plan safe edit order.

    This tool describes the PROTOCOL — Claude executes it using fs_search + fs_read.
    """
    import_patterns = {
        "python":     [r"^from\s+([\w\.]+)\s+import", r"^import\s+([\w\.]+)"],
        "typescript": [r"import\s+.*from\s+['\"]([^'\"]+)['\"]",
                       r"require\s*\(['\"]([^'\"]+)['\"]\)"],
        "javascript": [r"import\s+.*from\s+['\"]([^'\"]+)['\"]",
                       r"require\s*\(['\"]([^'\"]+)['\"]\)"],
    }
    patterns = import_patterns.get(language.lower(), import_patterns["python"])

    _log({"event": "cross_file_deps", "entry": entry_file, "lang": language})
    return json.dumps({
        "ok": True,
        "entry_file": entry_file,
        "root_path": root_path,
        "language": language,
        "max_depth": max_depth,
        "import_patterns": patterns,
        "protocol": [
            f"1. Read {entry_file} completely",
            "2. Extract all import statements matching the patterns above",
            "3. Resolve each import to an absolute file path relative to root_path",
            "4. For each resolved file: read it and repeat (up to max_depth levels)",
            "5. Build dependency map: {file: [files_it_imports]}",
            "6. Identify leaf files (no imports of local files) — edit these first",
            "7. Identify root file (entry_file) — edit this last",
            "8. Store the dependency map in mem_short_store key='dep_graph'",
        ],
        "output_format": {
            "dependency_map": {"file.py": ["dep1.py", "dep2.py"]},
            "edit_order": ["leaf files first, entry file last"],
            "circular_deps": [],
        },
    })

# ── Implementation Protocol ───────────────────────────────────────────────────

@mcp.tool()
def code_implement_protocol(
    task: str,
    language: str,
    files: list[str],
    has_tests: bool = False,
    complexity: str = "MEDIUM",
) -> str:
    """
    Return a step-by-step implementation protocol for Claude to follow.
    Claude executes this protocol — it is NOT a one-shot code generator.

    The protocol enforces: read→plan→implement→verify for every file.
    """
    steps = [
        {"step": 1, "action": "Scope confirmation",
         "detail": f"Restate the task in one sentence. Identify all files: {files}. "
                   "Call plan_scope_analysis if not already done.",
         "verify": "Scope is unambiguous and complete"},
        {"step": 2, "action": "Read all files",
         "detail": "Call fs_multi_read on all in-scope files. Do NOT start coding yet.",
         "verify": "Claude has read every file and can describe its current behaviour"},
        {"step": 3, "action": "Dependency analysis",
         "detail": "Call code_cross_file_deps to map import chains. "
                   "Identify safe edit order.",
         "verify": "Dependency map stored in short-term memory"},
        {"step": 4, "action": "Write/verify tests first (TDD)",
         "detail": "If has_tests=False: write failing tests before implementation. "
                   "If has_tests=True: run existing tests and confirm baseline.",
         "verify": "Tests exist and baseline is known"},
        {"step": 5, "action": "Implement — one file at a time",
         "detail": "Follow edit order from step 3. Per file: Read → Edit → Read again → Syntax check.",
         "verify": "Each file reads back correctly after edit"},
        {"step": 6, "action": "Cross-file integration check",
         "detail": "Re-read all modified files together. Check interfaces match. "
                   "Check all imports resolve.",
         "verify": "No broken interfaces or missing imports"},
        {"step": 7, "action": "Run tests",
         "detail": "Execute full test suite. Report pass/fail count.",
         "verify": "All tests pass OR known failures documented with root cause"},
        {"step": 8, "action": "Code review against checklist",
         "detail": f"Call code_review_checklist for each modified file.",
         "verify": "No CRITICAL or HIGH findings unresolved"},
        {"step": 9, "action": "Store decision in long-term memory",
         "detail": "Call mem_store_decision with key implementation choices.",
         "verify": "Decision stored"},
    ]
    if complexity == "LOW":
        steps = [s for s in steps if s["step"] in (1, 2, 5, 7)]

    _log({"event": "implement_protocol", "task": task[:80], "lang": language,
          "files": len(files), "complexity": complexity})
    return json.dumps({
        "ok": True, "task": task, "language": language,
        "files": files, "complexity": complexity,
        "protocol": steps,
        "anti_patterns": [
            "Writing code before reading all files",
            "Editing multiple files simultaneously without a plan",
            "Skipping tests because 'it looks right'",
            "Assuming an edit applied correctly without re-reading",
            "Inventing API signatures without checking documentation",
        ],
    }, indent=2)

# ── Complex Coding Scaffolder ─────────────────────────────────────────────────

@mcp.tool()
def code_scaffold(
    component_type: str,
    name: str,
    language: str,
    framework: str = "",
    output_path: str = "",
) -> str:
    """
    Generate a production-grade scaffold template for a component.
    component_type: api_endpoint|service|repository|model|middleware|
                    test_suite|cli_tool|mcp_server|agent|pipeline

    Returns the scaffold structure — Claude then generates the actual code
    and writes it via fs_write/fs_multi_write.
    """
    scaffolds = {
        "api_endpoint": {
            "files": [f"{output_path or '.'}/{name}.py",
                      f"{output_path or '.'}/tests/test_{name}.py"],
            "structure": {"router": "path, method, auth, validation, handler, response_model",
                          "handler": "parse → validate → call_service → map_response → return",
                          "tests": "happy_path, validation_error, auth_error, 500_error"},
        },
        "service": {
            "files": [f"{output_path or '.'}/{name}_service.py",
                      f"{output_path or '.'}/tests/test_{name}_service.py"],
            "structure": {"class": "init(deps), public_methods, private_helpers",
                          "error_handling": "domain exceptions, not HTTP exceptions",
                          "tests": "unit tests with mocked dependencies"},
        },
        "repository": {
            "files": [f"{output_path or '.'}/{name}_repo.py",
                      f"{output_path or '.'}/tests/test_{name}_repo.py"],
            "structure": {"interface": "abstract base class or protocol",
                          "implementation": "DB-specific implementation",
                          "methods": "get, get_by_id, list, create, update, delete"},
        },
        "mcp_server": {
            "files": [f"{output_path or '.'}/{name}/server.py",
                      f"{output_path or '.'}/{name}/requirements.txt"],
            "structure": {"imports": "fastmcp, stdlib only",
                          "tools": "@mcp.tool() decorated functions",
                          "entry": "mcp.run(transport='stdio')"},
        },
        "test_suite": {
            "files": [f"{output_path or '.'}/tests/test_{name}.py",
                      f"{output_path or '.'}/tests/conftest.py"],
            "structure": {"fixtures": "setup and teardown",
                          "happy_path": "normal expected flow",
                          "edge_cases": "empty, null, max, concurrent",
                          "error_cases": "invalid input, network failure, timeout"},
        },
    }
    scaffold = scaffolds.get(component_type, {"files": [], "structure": {}})
    _log({"event": "code_scaffold", "type": component_type, "name": name})
    return json.dumps({
        "ok": True, "component_type": component_type, "name": name,
        "language": language, "framework": framework,
        "files_to_create": scaffold.get("files", []),
        "structure": scaffold.get("structure", {}),
        "next_step": "Claude (T3) generates actual code for each file and calls fs_multi_write.",
    })

if __name__ == "__main__":
    mcp.run(transport="stdio")
