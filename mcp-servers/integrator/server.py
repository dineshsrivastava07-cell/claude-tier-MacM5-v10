#!/usr/bin/env python3
"""
DSR AI-Lab · Integrator MCP Server
QA, intelligent RCA, bug fixing, E2E integration verification.
FastMCP stdio. No API key. Subscription OAuth only.
"""
import json, re
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("dsr-integrator")

LOG_PATH = Path.home() / ".dsr-ai-lab" / "integrator" / "integrator.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def _log(e: dict) -> None:
    e["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_PATH, "a") as f: f.write(json.dumps(e) + "\n")

# ── Intelligent RCA ───────────────────────────────────────────────────────────

@mcp.tool()
def rca_analyze(
    error_message: str,
    stack_trace: str = "",
    context: str = "",
    language: str = "",
    files_involved: list[str] | None = None,
) -> str:
    """
    Intelligent Root Cause Analysis protocol.
    Returns a structured RCA framework Claude executes using actual file reads.

    Never hallucinates a root cause — protocol enforces evidence-based diagnosis.
    Every hypothesis must be verified against actual code before being stated as cause.
    """
    files = files_involved or []

    # Pattern-based hypothesis generation
    hypotheses = []
    err_lower = (error_message + " " + stack_trace).lower()

    if "import" in err_lower or "modulenotfound" in err_lower or "cannot find module" in err_lower:
        hypotheses.append({"id": "H1", "hypothesis": "Missing or misnamed import/dependency",
                           "verify": "Check import statement spelling, package installed, __init__.py present"})
    if "attributeerror" in err_lower or "is not a function" in err_lower or "undefined" in err_lower:
        hypotheses.append({"id": "H2", "hypothesis": "Object doesn't have the called attribute/method",
                           "verify": "Read the class definition — check method name, check if method was removed/renamed"})
    if "typeerror" in err_lower or "argument" in err_lower:
        hypotheses.append({"id": "H3", "hypothesis": "Wrong number or type of arguments passed",
                           "verify": "Compare function signature in definition with call site"})
    if "keyerror" in err_lower or "index" in err_lower or "out of range" in err_lower:
        hypotheses.append({"id": "H4", "hypothesis": "Missing key or out-of-bounds access",
                           "verify": "Trace data source — check if key/index always exists or needs guard"})
    if "timeout" in err_lower or "connection refused" in err_lower or "network" in err_lower:
        hypotheses.append({"id": "H5", "hypothesis": "Network/connection issue",
                           "verify": "Check service is running, check URL/port config, check firewall"})
    if "permission" in err_lower or "access denied" in err_lower or "forbidden" in err_lower:
        hypotheses.append({"id": "H6", "hypothesis": "Permission / authentication failure",
                           "verify": "Check auth token, file permissions, RBAC config"})
    if "null" in err_lower or "none" in err_lower or "undefined is not" in err_lower:
        hypotheses.append({"id": "H7", "hypothesis": "Unexpected None/null at call site",
                           "verify": "Trace where value originates — add null guard or fix upstream"})
    if "database" in err_lower or "sql" in err_lower or "unique" in err_lower or "constraint" in err_lower:
        hypotheses.append({"id": "H8", "hypothesis": "Database constraint or connection error",
                           "verify": "Check constraint definition, check input data, check connection pool"})

    if not hypotheses:
        hypotheses.append({"id": "H0", "hypothesis": "Unknown — requires manual trace",
                           "verify": "Read full stack trace line by line, read each file mentioned"})

    protocol = [
        "STEP 1: Read every file mentioned in the stack trace",
        "STEP 2: Locate the exact line number where the error originates",
        "STEP 3: Trace backwards: where does the failing value come from?",
        "STEP 4: Test each hypothesis against the actual code (not assumption)",
        "STEP 5: Identify root cause (not symptom) — one sentence statement",
        "STEP 6: Implement minimal fix — do not change unrelated code",
        "STEP 7: Verify fix resolves error without introducing new failures",
        "STEP 8: Call mem_store_error_fix to persist this error→fix pair",
    ]

    _log({"event": "rca_analyze", "error": error_message[:80], "hypotheses": len(hypotheses)})
    return json.dumps({
        "ok": True,
        "error_summary": error_message[:200],
        "has_stack_trace": bool(stack_trace),
        "files_to_read": files,
        "hypotheses": hypotheses,
        "rca_protocol": protocol,
        "output_format": {
            "root_cause": "One sentence — the actual cause, not the symptom",
            "evidence": "Exact file + line that proves the root cause",
            "fix": "Minimal change required",
            "prevention": "How to prevent recurrence",
        },
        "anti_patterns": [
            "Stating a root cause before reading the failing code",
            "Fixing the symptom (the exception line) rather than the root cause",
            "Changing multiple things at once — isolate the fix",
            "Assuming the error message describes the root cause exactly",
        ],
    }, indent=2)

# ── Intelligent Bug Fix Protocol ──────────────────────────────────────────────

@mcp.tool()
def bug_fix_protocol(
    bug_description: str,
    reproduction_steps: str = "",
    expected: str = "",
    actual: str = "",
    files_suspected: list[str] | None = None,
) -> str:
    """
    Structured bug fix protocol. Enforces root cause identification before any code change.
    Claude follows this protocol — does NOT jump to fixing immediately.
    """
    files = files_suspected or []
    _log({"event": "bug_fix_protocol", "bug": bug_description[:80]})
    return json.dumps({
        "ok": True,
        "bug": bug_description,
        "protocol": [
            {"phase": "REPRODUCE", "actions": [
                "Understand reproduction_steps exactly",
                "Confirm you can describe what should happen (expected) vs what does happen (actual)",
                "Identify the entry point where the bug manifests",
            ]},
            {"phase": "LOCATE", "actions": [
                f"Read all suspected files: {files}",
                "Find the exact code path that is triggered by reproduction_steps",
                "Add mental breakpoints: what is the value at each step?",
            ]},
            {"phase": "ROOT_CAUSE", "actions": [
                "Call rca_analyze with the specific error or failure point",
                "State root cause in one sentence before writing any fix",
                "Verify root cause against code — never assume",
            ]},
            {"phase": "FIX", "actions": [
                "Write the minimal fix — touch only what is necessary",
                "Read the file before editing",
                "Read the file after editing to confirm correctness",
                "Verify fix does not break adjacent behaviour",
            ]},
            {"phase": "VERIFY", "actions": [
                "Re-run reproduction_steps mentally against the fix",
                "Run relevant tests",
                "Check no regressions in files that import the fixed file",
            ]},
            {"phase": "DOCUMENT", "actions": [
                "Call mem_store_error_fix to persist this bug→fix pair",
                "Note prevention strategy for future reference",
            ]},
        ],
        "ground_rules": [
            "Never write a fix before stating the root cause",
            "Never fix multiple bugs in one commit",
            "Never assume the bug is where the error message says — trace upstream",
        ],
    }, indent=2)

# ── QA Review Protocol ────────────────────────────────────────────────────────

@mcp.tool()
def qa_review(
    scope: str,
    files: list[str],
    test_files: list[str] | None = None,
    qa_type: str = "pre_commit",
) -> str:
    """
    QA review protocol.
    qa_type: pre_commit|pre_release|regression|integration|security_scan

    Returns a structured QA checklist Claude executes against actual code + tests.
    """
    test_files = test_files or []
    checklists = {
        "pre_commit": [
            "Syntax valid on all modified files",
            "No debug statements (print, console.log, debugger) left in",
            "All new functions have tests",
            "Modified functions: existing tests still pass",
            "No hardcoded credentials or secrets",
            "Type errors: none (run mypy/tsc if applicable)",
            "Linting: no new warnings introduced",
        ],
        "pre_release": [
            "All pre_commit checks pass",
            "Integration tests pass in staging environment",
            "No open CRITICAL or HIGH code review findings",
            "API contracts match documentation",
            "Migration scripts tested on copy of production data",
            "Rollback procedure documented and tested",
            "Monitoring/alerting in place for new code paths",
            "Performance regression: none (compare benchmarks)",
        ],
        "regression": [
            "All previously passing tests still pass",
            "No new test failures introduced by this change",
            "Behaviour unchanged for unmodified code paths",
            "Edge cases still handled: empty input, null, max, concurrent",
        ],
        "integration": [
            "All integration points verified end-to-end",
            "External service mocks replaced with real services for integration test",
            "Error responses from each integration handled correctly",
            "Timeouts and retries configured and tested",
            "Data contracts between services verified",
        ],
        "security_scan": [
            "No SQL injection vectors (parameterised queries everywhere)",
            "No XSS vectors (output escaped everywhere)",
            "Authentication required on all protected endpoints",
            "Rate limiting configured on public endpoints",
            "Sensitive data not logged",
            "Dependencies scanned: no known CVEs",
            "Secrets not committed to git",
        ],
    }
    checklist = checklists.get(qa_type, checklists["pre_commit"])
    _log({"event": "qa_review", "type": qa_type, "files": len(files)})
    return json.dumps({
        "ok": True, "qa_type": qa_type, "scope": scope,
        "files_to_review": files, "test_files": test_files,
        "checklist": checklist,
        "output_format": {
            "results": [{"check": "", "status": "PASS|FAIL|SKIP", "detail": ""}],
            "verdict": "PASS|FAIL|NEEDS_WORK",
            "blockers": [], "warnings": [],
        },
        "instruction": (
            "Execute every check. Do not skip. "
            "FAIL items are blockers — fix before declaring QA complete. "
            "Store QA outcome in mem_long_store category=qa."
        ),
    }, indent=2)

# ── E2E Integration Verification ─────────────────────────────────────────────

@mcp.tool()
def integration_verify(
    system_name: str,
    integration_points: list[dict],
    environment: str = "local",
) -> str:
    """
    E2E integration verification protocol.
    integration_points: list of {name, type, endpoint, auth, expected_response}
    type: http_api|database|message_queue|file_system|subprocess

    Claude follows this to verify every integration point is wired correctly.
    """
    _log({"event": "integration_verify", "system": system_name,
          "points": len(integration_points), "env": environment})

    per_point_protocol = []
    for ip in integration_points:
        itype = ip.get("type", "http_api")
        checks = {
            "http_api": [
                f"Verify endpoint reachable: {ip.get('endpoint', '?')}",
                "Auth header/token valid and not expired",
                "Request schema matches API contract",
                "Response schema matches expected structure",
                "Error responses (4xx, 5xx) handled correctly",
                "Timeout configured (not infinite)",
            ],
            "database": [
                "Connection string valid for environment",
                "Connection pool configured correctly",
                "Schema migrations applied",
                "Read/write permissions verified",
                "Transaction rollback works on error",
            ],
            "message_queue": [
                "Queue/topic exists and is accessible",
                "Producer can publish without error",
                "Consumer receives and deserialises correctly",
                "Dead-letter queue configured for failures",
                "Idempotency key prevents duplicate processing",
            ],
            "file_system": [
                "Target directory exists and is writable",
                "File creation and read-back verified",
                "Error on missing file handled gracefully",
            ],
        }.get(itype, ["Verify connection", "Verify read", "Verify write", "Verify error handling"])

        per_point_protocol.append({
            "integration": ip.get("name", itype),
            "type": itype,
            "environment": environment,
            "checks": checks,
        })

    return json.dumps({
        "ok": True, "system": system_name, "environment": environment,
        "integration_points": per_point_protocol,
        "overall_protocol": [
            "Verify each integration point independently first",
            "Then verify full end-to-end flow with all points active",
            "Simulate failure of each integration point — verify graceful degradation",
            "Record all integration outcomes in long-term memory",
        ],
    }, indent=2)

# ── Issue Fixer ───────────────────────────────────────────────────────────────

@mcp.tool()
def fix_issues_from_qa(
    qa_findings: list[dict],
    priority_order: str = "CRITICAL,HIGH,MEDIUM,LOW",
) -> str:
    """
    Generate an ordered fix plan from QA findings.
    qa_findings: list of {severity, file, line, issue, fix_hint}

    Returns a fix sequence Claude executes: one fix per file, verify after each.
    """
    order = [s.strip() for s in priority_order.split(",")]
    severity_rank = {s: i for i, s in enumerate(order)}

    sorted_findings = sorted(
        qa_findings,
        key=lambda x: severity_rank.get(x.get("severity", "LOW"), 99)
    )

    fix_plan = []
    for i, finding in enumerate(sorted_findings):
        fix_plan.append({
            "fix_id": f"F{i+1:03d}",
            "severity": finding.get("severity"),
            "file": finding.get("file"),
            "line": finding.get("line"),
            "issue": finding.get("issue"),
            "fix_hint": finding.get("fix_hint", ""),
            "protocol": [
                f"Read {finding.get('file')} completely",
                f"Locate issue at line {finding.get('line')}",
                "Apply minimal fix",
                "Read file again to verify fix",
                "Run tests for this file",
            ],
        })

    _log({"event": "fix_issues", "findings": len(qa_findings)})
    return json.dumps({
        "ok": True,
        "total_findings": len(qa_findings),
        "fix_plan": fix_plan,
        "rule": "Fix CRITICAL first. Verify each fix before moving to next. "
                "Never fix multiple files simultaneously without a plan.",
    }, indent=2)

if __name__ == "__main__":
    mcp.run(transport="stdio")
