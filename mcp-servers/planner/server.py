#!/usr/bin/env python3
"""
DSR AI-Lab · Planner MCP Server
Global deep review, architecture creation, phase plans, step-by-step TODOs.
Long-context aware. FastMCP stdio. No API key. Subscription OAuth only.
"""
import json, time
from datetime import datetime
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

mcp = FastMCP("dsr-planner")

LOG_PATH = Path.home() / ".dsr-ai-lab" / "planner" / "plans.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def _log(entry: dict) -> None:
    entry["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ── Complexity & Scope Analysis ───────────────────────────────────────────────

@mcp.tool()
def plan_scope_analysis(
    description: str,
    known_files: list[str] | None = None,
    known_systems: list[str] | None = None,
    constraints: str = "",
) -> str:
    """
    Analyse scope, complexity, and intent of a task or project BEFORE any work begins.
    Returns structured analysis: complexity rating, risk flags, recommended approach.

    Call this FIRST for any task scored T3 by the tier gate.
    Claude uses this to build an accurate mental model before writing a single line.

    Args:
        description:    Full task/project description (can be long — 200K ctx supported)
        known_files:    Files already identified as in-scope
        known_systems:  External systems, APIs, services involved
        constraints:    Hard constraints (deadline, tech stack, no-change zones)
    """
    files   = known_files   or []
    systems = known_systems or []

    # Complexity signals
    signals = []
    desc_lower = description.lower()

    if any(w in desc_lower for w in ["auth", "oauth", "jwt", "security", "encrypt"]):
        signals.append({"signal": "SECURITY", "weight": "HIGH",
                        "note": "Security-critical path — T3 mandatory, extra review required"})
    if any(w in desc_lower for w in ["migration", "migrate", "rollback", "production"]):
        signals.append({"signal": "PRODUCTION_OPS", "weight": "HIGH",
                        "note": "Production operation — dry-run and rollback plan required"})
    if len(files) > 8:
        signals.append({"signal": "MULTI_FILE", "weight": "MEDIUM",
                        "note": f"{len(files)} files in scope — phased editing recommended"})
    if len(systems) > 2:
        signals.append({"signal": "MULTI_SYSTEM", "weight": "HIGH",
                        "note": f"{len(systems)} systems — integration contracts must be defined first"})
    if any(w in desc_lower for w in ["design", "architect", "from scratch", "new system"]):
        signals.append({"signal": "GREENFIELD", "weight": "HIGH",
                        "note": "Novel design — architecture phase required before implementation"})
    if any(w in desc_lower for w in ["refactor", "rewrite", "restructure"]):
        signals.append({"signal": "REFACTOR", "weight": "MEDIUM",
                        "note": "Refactor scope — read all affected files before proposing changes"})

    complexity = "LOW"
    if len(signals) >= 1: complexity = "MEDIUM"
    if len(signals) >= 2: complexity = "HIGH"
    if any(s["weight"] == "HIGH" for s in signals): complexity = "HIGH"
    if len(signals) >= 3 and any(s["weight"] == "HIGH" for s in signals):
        complexity = "CRITICAL"

    result = {
        "ok": True,
        "complexity": complexity,
        "signals": signals,
        "files_in_scope": files,
        "systems_in_scope": systems,
        "constraints": constraints,
        "recommended_approach": _recommend_approach(complexity, signals),
        "required_phases": _required_phases(complexity, signals),
        "analysis_ts": datetime.utcnow().isoformat() + "Z",
    }
    _log({"event": "scope_analysis", "complexity": complexity, "signals_count": len(signals)})
    return json.dumps(result, indent=2)

def _recommend_approach(complexity: str, signals: list) -> str:
    has_security   = any(s["signal"] == "SECURITY" for s in signals)
    has_greenfield = any(s["signal"] == "GREENFIELD" for s in signals)
    has_prod_ops   = any(s["signal"] == "PRODUCTION_OPS" for s in signals)

    if complexity == "CRITICAL":
        return ("FULL_LIFECYCLE: scope → architecture → phase_plan → todos → implement → "
                "qa → rca_ready → integrate → verify. No steps skippable.")
    if has_greenfield:
        return "DESIGN_FIRST: architecture → ADRs → phase_plan → implement → qa"
    if has_prod_ops:
        return "OPS_SAFE: dry-run → backup → phase_plan → implement → verify → rollback_plan"
    if has_security:
        return "SECURITY_FIRST: threat_model → implement → security_review → qa"
    if complexity == "HIGH":
        return "STRUCTURED: scope → plan_phases → todos → implement → qa"
    return "STANDARD: read_all → implement → verify"

def _required_phases(complexity: str, signals: list) -> list[str]:
    base = ["scope_analysis", "plan_todos", "implement", "qa_review"]
    if complexity in ("HIGH", "CRITICAL"):
        base = ["scope_analysis", "plan_architecture", "plan_phases", "plan_todos",
                "implement", "qa_review", "rca_check", "integration_verify"]
    return base

# ── Architecture Creation ─────────────────────────────────────────────────────

@mcp.tool()
def plan_architecture(
    system_name: str,
    requirements: str,
    tech_stack: str = "",
    constraints: str = "",
    existing_systems: str = "",
    output_format: str = "full",
) -> str:
    """
    Generate a structured architecture document.
    output_format: full|summary|adr (Architecture Decision Record)

    Produces:
    - Component breakdown with responsibilities
    - Data flow description
    - Integration points
    - Technology decisions with rationale
    - Risk register
    - Non-functional requirements mapping
    """
    now = datetime.utcnow().isoformat() + "Z"

    architecture = {
        "ok": True,
        "system": system_name,
        "created_at": now,
        "format": output_format,
        "sections": {
            "overview": {
                "description": "Fill from requirements analysis",
                "requirements_summary": requirements[:500],
                "tech_stack": tech_stack,
                "constraints": constraints,
            },
            "components": {
                "instruction": (
                    "Claude (T3) must enumerate each component with: "
                    "name | responsibility | interfaces | dependencies | tier(frontend/backend/data/infra)"
                ),
                "template": {
                    "component_name": {"responsibility": "", "interfaces": [],
                                       "dependencies": [], "tier": ""},
                }
            },
            "data_flow": {
                "instruction": "Map request/response paths between components. Include async flows.",
            },
            "integration_points": {
                "instruction": (
                    "For each external system in: " + (existing_systems or "none") +
                    " — define: protocol, auth method, contract, failure mode, timeout"
                ),
            },
            "technology_decisions": {
                "instruction": "ADR per major tech choice: Context → Decision → Rationale → Consequences",
            },
            "non_functional_requirements": {
                "performance":   "latency targets, throughput",
                "scalability":   "growth assumptions",
                "security":      "auth model, data classification",
                "observability": "logging, metrics, tracing",
                "reliability":   "SLA, failover strategy",
            },
            "risk_register": {
                "instruction": (
                    "List risks as: risk | probability(H/M/L) | impact(H/M/L) | mitigation"
                ),
            },
        },
        "next_step": "Call plan_phases with this architecture as input.",
    }

    _log({"event": "plan_architecture", "system": system_name, "format": output_format})
    return json.dumps(architecture, indent=2)

# ── Phase Planning ────────────────────────────────────────────────────────────

@mcp.tool()
def plan_phases(
    project_name: str,
    scope: str,
    total_complexity: str = "HIGH",
    team_size: int = 1,
    sprint_days: int = 14,
) -> str:
    """
    Generate a phased implementation plan with milestones, dependencies, and exit criteria.

    total_complexity: LOW|MEDIUM|HIGH|CRITICAL
    team_size: number of developers (affects phase sizing)
    sprint_days: sprint/iteration length in days
    """
    phase_templates = {
        "LOW":    ["Phase 1: Implement", "Phase 2: Test & Verify"],
        "MEDIUM": ["Phase 1: Design & Setup", "Phase 2: Core Implementation",
                   "Phase 3: Integration & Test"],
        "HIGH":   ["Phase 1: Architecture & ADRs", "Phase 2: Foundation & Scaffolding",
                   "Phase 3: Core Domain Implementation", "Phase 4: Integration",
                   "Phase 5: QA & Hardening", "Phase 6: Production Readiness"],
        "CRITICAL": ["Phase 0: Spike & Risk Reduction", "Phase 1: Architecture & ADRs",
                     "Phase 2: Foundation", "Phase 3: Core A (MVP)",
                     "Phase 4: Core B (Full)", "Phase 5: Integration",
                     "Phase 6: Security Review", "Phase 7: QA & Load Test",
                     "Phase 8: Production Readiness & Runbook"],
    }
    phases = phase_templates.get(total_complexity, phase_templates["HIGH"])

    plan = {
        "ok": True,
        "project": project_name,
        "scope_summary": scope[:300],
        "complexity": total_complexity,
        "sprint_days": sprint_days,
        "phases": [],
    }
    for i, name in enumerate(phases):
        plan["phases"].append({
            "id": f"P{i}",
            "name": name,
            "sprint": i + 1,
            "estimated_days": sprint_days,
            "objectives": ["Claude (T3) must fill from scope analysis"],
            "deliverables": ["Claude (T3) must define concrete, verifiable outputs"],
            "exit_criteria": ["All tests passing", "Code reviewed", "Docs updated"],
            "dependencies": [f"P{i-1}"] if i > 0 else [],
            "risks": [],
        })

    plan["total_estimated_days"] = len(phases) * sprint_days
    plan["next_step"] = "Call plan_todos for each phase to generate step-by-step task lists."
    _log({"event": "plan_phases", "project": project_name, "phases": len(phases)})
    return json.dumps(plan, indent=2)

# ── Step-by-Step TODO Planning ────────────────────────────────────────────────

@mcp.tool()
def plan_todos(
    phase_name: str,
    phase_objective: str,
    files_involved: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> str:
    """
    Generate a granular, ordered, executable TODO list for a single phase.
    Each TODO is: action | file | acceptance_criterion | tier | blocking_on

    Rules embedded in output:
    - Every TODO must be verifiable (has an acceptance criterion)
    - Every TODO has a tier assignment (T1/T2/T3)
    - TODOs are ordered by dependency
    - Blocking TODOs are flagged
    """
    files = files_involved or []
    deps  = dependencies   or []

    template_todos = [
        {"id": "T001", "action": "Read and understand all files in scope",
         "files": files, "acceptance": "Claude can describe current behaviour of each file",
         "tier": "T3", "blocking_on": [], "blocking_for": ["T002"]},
        {"id": "T002", "action": "Identify all cross-file dependencies and contracts",
         "files": files, "acceptance": "Dependency graph documented in short-term memory",
         "tier": "T3", "blocking_on": ["T001"], "blocking_for": ["T003"]},
        {"id": "T003", "action": "Write failing tests (TDD) or define acceptance test plan",
         "files": ["tests/"], "acceptance": "Tests exist and fail for expected reasons",
         "tier": "T2", "blocking_on": ["T002"], "blocking_for": ["T004"]},
        {"id": "T004", "action": "Implement changes — one file at a time, read-edit-verify loop",
         "files": files, "acceptance": "All edited files syntax-valid, tests passing",
         "tier": "T2", "blocking_on": ["T003"], "blocking_for": ["T005"]},
        {"id": "T005", "action": "Cross-file integration check",
         "files": files, "acceptance": "No broken imports, interfaces match contracts",
         "tier": "T3", "blocking_on": ["T004"], "blocking_for": ["T006"]},
        {"id": "T006", "action": "QA review and RCA for any failures",
         "files": [], "acceptance": "Zero known failures. Failures documented with root cause.",
         "tier": "T3", "blocking_on": ["T005"], "blocking_for": []},
    ]

    result = {
        "ok": True,
        "phase": phase_name,
        "objective": phase_objective,
        "files_in_scope": files,
        "external_dependencies": deps,
        "todos": template_todos,
        "execution_rules": [
            "Never mark a TODO complete without verifying its acceptance criterion",
            "Re-read files before editing if > 5 turns have passed since last read",
            "Never skip T001 and T002 — they are always blocking",
            "Log each completed TODO to mem_short_store with key=todo_{id}",
            "On any failure: call integrator rca_analyze before retrying",
        ],
        "next_step": "Execute TODOs in order. Use tier_gate_classify per TODO before execution.",
    }
    _log({"event": "plan_todos", "phase": phase_name, "todos": len(template_todos)})
    return json.dumps(result, indent=2)

# ── Deep Review ───────────────────────────────────────────────────────────────

@mcp.tool()
def plan_deep_review(
    subject: str,
    context: str,
    review_type: str = "code",
    files_to_review: list[str] | None = None,
) -> str:
    """
    Initiate a structured deep review with long-context awareness.
    review_type: code|architecture|integration|security|performance|qa

    Returns a review protocol Claude must follow — not the review itself.
    Claude executes the review using this protocol + actual file reads.
    """
    protocols = {
        "code": [
            "Read every file in scope completely before commenting on any",
            "Identify all entry points, exports, and public interfaces",
            "Check for: unused imports, dead code, inconsistent naming, missing error handling",
            "Verify: all functions have docstrings, type hints present, tests exist",
            "Flag: security anti-patterns, hardcoded values, missing input validation",
            "Output: structured finding per file with severity (CRITICAL/HIGH/MEDIUM/LOW/INFO)",
        ],
        "architecture": [
            "Map all component dependencies — draw the dependency graph mentally",
            "Verify: no circular dependencies, clear separation of concerns",
            "Check: all integration contracts are explicit and documented",
            "Flag: single points of failure, missing error boundaries, scalability blockers",
            "Verify: observability (logging, metrics, tracing) at each layer",
        ],
        "security": [
            "Review all authentication and authorisation paths",
            "Check: input validation at every external boundary",
            "Flag: SQL injection, XSS, CSRF, insecure deserialization risks",
            "Verify: secrets not hardcoded, not in logs, not in error messages",
            "Check: dependency versions against known CVEs",
            "Output: finding with CWE reference where applicable",
        ],
        "integration": [
            "List all integration points: API calls, DB queries, message queues, file I/O",
            "Verify: each integration has timeout, retry, and circuit-breaker logic",
            "Check: error responses are handled and not swallowed",
            "Verify: contracts match between producer and consumer",
            "Flag: missing idempotency on retryable operations",
        ],
        "performance": [
            "Identify hot paths — code called in loops or on every request",
            "Flag: N+1 queries, missing indices, unbounded result sets",
            "Check: unnecessary serialization/deserialization in hot paths",
            "Verify: caching strategy where latency-sensitive",
            "Flag: blocking I/O in async contexts",
        ],
        "qa": [
            "Verify: test coverage exists for all public interfaces",
            "Check: tests are deterministic (no time-dependent, no random)",
            "Flag: tests that test implementation rather than behaviour",
            "Verify: edge cases covered: empty input, null, max values, concurrency",
            "Check: integration tests exist for all external dependencies",
        ],
    }

    protocol = protocols.get(review_type, protocols["code"])
    result = {
        "ok": True,
        "review_type": review_type,
        "subject": subject,
        "context_summary": context[:200],
        "files_to_review": files_to_review or [],
        "review_protocol": protocol,
        "output_format": {
            "per_file": {"file": "", "findings": [{"severity": "", "location": "",
                         "issue": "", "recommendation": ""}]},
            "summary": {"total_findings": 0, "critical": 0, "high": 0, "medium": 0,
                        "low": 0, "verdict": "PASS|FAIL|NEEDS_WORK"},
        },
        "instructions": (
            "Execute this protocol now using fs_multi_read to load all files. "
            "Do not output findings until all files are read. "
            "Apply every checklist item to every file."
        ),
    }
    _log({"event": "deep_review", "type": review_type, "files": len(files_to_review or [])})
    return json.dumps(result, indent=2)

if __name__ == "__main__":
    mcp.run(transport="stdio")
