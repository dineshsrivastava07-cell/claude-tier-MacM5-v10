#!/usr/bin/env python3
"""
DSR AI-Lab · Skills MCP Server
Global intelligent skills registry. Skills are structured protocols Claude
applies to tasks — not code templates. FastMCP stdio. No API key.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP

mcp = FastMCP("dsr-skills")

# Resolve path: env var (set in settings.json) → legacy hardcoded fallback
_env_path = os.environ.get("SKILLS_PATH") or os.environ.get("SKILLS_REGISTRY")
SKILLS_PATH = Path(_env_path) if _env_path else Path.home() / "dsr-ai-lab" / "skills-registry" / "global-skills.json"
LOG_PATH    = Path.home() / ".dsr-ai-lab" / "skills" / "skills.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def _log(e: dict) -> None:
    e["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_PATH, "a") as f: f.write(json.dumps(e) + "\n")

def _normalize(data: dict) -> dict:
    """Normalize v10.1 array format {version, skills:[...]} to flat dict {skill_id: {...}}."""
    if isinstance(data.get("skills"), list):
        result = {}
        for skill in data["skills"]:
            sid = skill.get("id", "unknown")
            result[sid] = {
                "name": sid,
                "trigger": ", ".join(skill.get("trigger_keywords", [])),
                "description": skill.get("description", ""),
                "steps": skill.get("protocol", []),
                "tools": [],
                "anti_patterns": [],
                "slash_command": skill.get("slash_command"),
                "default_tier_hint": skill.get("default_tier_hint"),
            }
        return result
    # Old flat format — return as-is (strip metadata keys)
    return {k: v for k, v in data.items() if not k.startswith("_") and k != "version"}

def _load_skills() -> dict:
    if SKILLS_PATH.exists():
        try:
            return _normalize(json.loads(SKILLS_PATH.read_text()))
        except Exception:
            pass
    return _builtin_skills()

def _builtin_skills() -> dict:
    return {
        "deep_review": {
            "name": "Deep Review",
            "trigger": "Any review, audit, or analysis task",
            "description": "Long-context aware review. Read ALL files first, never comment before complete read.",
            "steps": ["Read all in-scope files", "Build mental model of full system",
                      "Apply review checklist", "Output structured findings with severity",
                      "Provide prioritised recommendations"],
            "tools": ["plan_deep_review", "fs_multi_read", "code_review_checklist"],
            "anti_patterns": ["Reviewing file-by-file without full context",
                              "Commenting on partial code view"],
        },
        "architecture": {
            "name": "Architecture Creation",
            "trigger": "System design, new component, greenfield project",
            "description": "Requirements → ADRs → Component diagram → Data flow → Risk register",
            "steps": ["Gather requirements", "Identify components and responsibilities",
                      "Define integration contracts", "Document technology decisions",
                      "Create risk register", "Define non-functional requirements"],
            "tools": ["plan_scope_analysis", "plan_architecture", "mem_store_decision"],
            "anti_patterns": ["Designing without constraints", "Skipping ADRs",
                              "Starting implementation before architecture is agreed"],
        },
        "phase_plan": {
            "name": "Phase Planning",
            "trigger": "Any project or feature requiring multiple implementation steps",
            "description": "Break work into phases with milestones, dependencies, exit criteria",
            "steps": ["Scope analysis", "Identify phases", "Define deliverables per phase",
                      "Assign exit criteria", "Identify cross-phase dependencies"],
            "tools": ["plan_scope_analysis", "plan_phases", "plan_todos"],
            "anti_patterns": ["Single phase for all work", "Phases without exit criteria",
                              "Missing dependency tracking between phases"],
        },
        "todo_plan": {
            "name": "Step-by-Step TODO Planning",
            "trigger": "Before starting any implementation",
            "description": "Atomic, ordered, verifiable TODO list. Each TODO has: action, file, acceptance criterion, tier.",
            "steps": ["Read all files first", "Identify smallest units of work",
                      "Assign tier to each TODO", "Order by dependency",
                      "Define acceptance criterion per TODO"],
            "tools": ["plan_todos", "tier_gate_classify"],
            "anti_patterns": ["TODOs without acceptance criteria", "Un-ordered TODOs",
                              "TODOs that span multiple files without a plan"],
        },
        "coding": {
            "name": "Standard Coding",
            "trigger": "Single-file or simple multi-file coding task",
            "description": "Read → Plan → Implement → Verify. Never code before reading.",
            "steps": ["Read file(s)", "State what you will change and why",
                      "Implement change", "Read file again to verify",
                      "Run relevant tests"],
            "tools": ["fs_read", "fs_patch", "code_review_checklist"],
            "anti_patterns": ["Coding from memory without reading current file",
                              "Not verifying edit was applied correctly"],
        },
        "complex_coding": {
            "name": "Complex Coding",
            "trigger": "Multi-file feature, refactor, or algorithm implementation",
            "description": "Full protocol: scope → deps → implement in order → cross-check → qa",
            "steps": ["Scope analysis", "Read ALL files", "Map dependencies",
                      "Write tests first", "Implement in dependency order",
                      "Cross-file integration check", "QA review"],
            "tools": ["code_cross_file_deps", "code_multi_file_plan",
                      "code_implement_protocol", "qa_review"],
            "anti_patterns": ["Editing files in arbitrary order",
                              "Skipping dependency analysis for multi-file changes"],
        },
        "multi_file_edit": {
            "name": "Multi-File Edit",
            "trigger": "Changes spanning 2+ files",
            "description": "Plan edit order → Read all → Edit one at a time → Verify each → Integration check",
            "steps": ["List all files in scope", "Classify each file by role",
                      "Determine safe edit order", "Read → Edit → Verify per file",
                      "Final cross-file consistency check"],
            "tools": ["code_multi_file_plan", "fs_multi_read", "code_cross_file_deps"],
            "anti_patterns": ["Editing multiple files without a plan",
                              "Not verifying each file after edit",
                              "Skipping final integration check"],
        },
        "e2e_integration": {
            "name": "E2E Integration",
            "trigger": "Wiring services together, API contracts, cross-system integration",
            "description": "Define contracts → Implement → Verify each point → Test failure paths",
            "steps": ["List all integration points", "Define request/response contracts",
                      "Implement with timeouts and error handling",
                      "Verify each integration point independently",
                      "Test full end-to-end flow", "Test graceful failure of each point"],
            "tools": ["integration_verify", "qa_review"],
            "anti_patterns": ["Assuming integration works without testing",
                              "Missing timeout/retry on external calls",
                              "Not testing failure paths"],
        },
        "qa": {
            "name": "Detailed QA",
            "trigger": "Before any commit, PR, or release",
            "description": "Structured QA covering: syntax, tests, security, integration, performance",
            "steps": ["Run qa_review with appropriate qa_type",
                      "Fix all CRITICAL findings before proceeding",
                      "Fix all HIGH findings before release",
                      "Document MEDIUM and LOW as known issues"],
            "tools": ["qa_review", "code_review_checklist", "fix_issues_from_qa"],
            "anti_patterns": ["Skipping QA 'because tests pass'",
                              "Declaring PASS with open CRITICAL findings"],
        },
        "rca": {
            "name": "Intelligent RCA",
            "trigger": "Any error, failure, or unexpected behaviour",
            "description": "Evidence-based root cause analysis. No hypotheses without code evidence.",
            "steps": ["Read stack trace carefully", "Identify exact failure line",
                      "Trace value origins backwards", "Generate hypotheses",
                      "Verify each hypothesis against actual code",
                      "State root cause with evidence", "Apply minimal fix"],
            "tools": ["rca_analyze", "bug_fix_protocol", "mem_store_error_fix"],
            "anti_patterns": ["Fixing the symptom not the root cause",
                              "Stating root cause before reading code",
                              "Changing multiple things at once"],
        },
        "bug_fix": {
            "name": "Intelligent Bug Fix",
            "trigger": "Any bug report or unexpected behaviour",
            "description": "Reproduce → Locate → Root cause → Minimal fix → Verify → Document",
            "steps": ["Understand reproduction steps", "Locate failure in code",
                      "Identify root cause (call rca_analyze)",
                      "Write fix (minimal — one change)", "Verify fix",
                      "Store in long-term memory"],
            "tools": ["bug_fix_protocol", "rca_analyze", "mem_store_error_fix"],
            "anti_patterns": ["Fixing without reproducing", "Guessing the fix",
                              "Not documenting the fix for future reference"],
        },
        "implementation": {
            "name": "Intelligent Implementation",
            "trigger": "Any feature or system implementation task",
            "description": "Full lifecycle: scope → architecture → plan → implement → qa → memory",
            "steps": ["Scope analysis", "Architecture if new system",
                      "Phase and TODO plan", "Implement per plan",
                      "QA review", "Fix issues", "Store decisions"],
            "tools": ["agent_implement", "plan_scope_analysis", "plan_todos",
                      "code_implement_protocol", "qa_review"],
            "anti_patterns": ["Implementing without a plan",
                              "Skipping QA because implementation 'looks right'"],
        },
        "agentic": {
            "name": "Intelligent Agentic",
            "trigger": "Complex autonomous task requiring multiple steps and tools",
            "description": "Goal → Decompose → Orchestrate subagents → Verify → Memory",
            "steps": ["State goal unambiguously", "Decompose into atomic subtasks",
                      "Assign tier to each subtask", "Orchestrate in dependency order",
                      "Verify each subagent output", "QA final result",
                      "Update long-term memory"],
            "tools": ["agent_decompose", "agent_spawn_subagent", "agent_orchestrate",
                      "agent_implement"],
            "anti_patterns": ["Subagents expanding their scope",
                              "Not verifying subagent output before using it",
                              "Missing memory update at completion"],
        },
        "subagent": {
            "name": "Intelligent Subagent",
            "trigger": "When Claude is operating as a subagent within a larger orchestration",
            "description": "Bounded execution: only declared tools, only declared scope, structured output only",
            "steps": ["Read and confirm scope boundaries",
                      "Execute ONLY the declared subtask",
                      "Use ONLY the declared tools",
                      "Return structured output — do not apply changes autonomously",
                      "Escalate if scope needs to expand"],
            "tools": ["agent_spawn_subagent"],
            "anti_patterns": ["Expanding scope beyond subtask",
                              "Using tools not in declared allowed list",
                              "Self-applying results without reporting back"],
        },
    }

@mcp.tool()
def skill_lookup(task_description: str) -> str:
    """
    Intelligently match a task description to the most relevant skill(s).
    Returns the skill protocol Claude should apply.
    Call this early in complex sessions to load the right operating protocol.
    """
    skills = _load_skills()
    desc_lower = task_description.lower()

    scored: list[tuple[int, str, dict]] = []
    for skill_id, skill in skills.items():
        score = 0
        triggers = [skill.get("trigger", ""), skill.get("name", "")]
        keywords = skill_id.replace("_", " ").split()
        for trigger in triggers:
            if any(w in desc_lower for w in trigger.lower().split()):
                score += 2
        for kw in keywords:
            if kw in desc_lower:
                score += 1
        if score > 0:
            scored.append((score, skill_id, skill))

    scored.sort(key=lambda x: -x[0])
    top = scored[:3] if scored else [(0, "implementation", skills.get("implementation", {}))]

    _log({"event": "skill_lookup", "task": task_description[:80],
          "matched": [s[1] for s in top]})
    return json.dumps({
        "ok": True,
        "matched_skills": [{"skill_id": s[1], "score": s[0],
                            "name": s[2].get("name"),
                            "trigger": s[2].get("trigger"),
                            "steps": s[2].get("steps"),
                            "tools": s[2].get("tools"),
                            "anti_patterns": s[2].get("anti_patterns")}
                           for s in top],
        "instruction": "Apply the highest-scored skill's steps as your operating protocol for this task.",
    }, indent=2)

@mcp.tool()
def skill_get(skill_id: str) -> str:
    """Retrieve a specific skill by ID."""
    skills = _load_skills()
    skill = skills.get(skill_id)
    if not skill:
        return json.dumps({"ok": False, "error": f"Skill '{skill_id}' not found",
                           "available": list(skills.keys())})
    _log({"event": "skill_get", "skill_id": skill_id})
    return json.dumps({"ok": True, "skill_id": skill_id, **skill})

@mcp.tool()
def skill_list() -> str:
    """List all available skills with name and trigger."""
    skills = _load_skills()
    return json.dumps({
        "ok": True,
        "skills": {sid: {"name": s.get("name"), "trigger": s.get("trigger")}
                   for sid, s in skills.items()},
        "count": len(skills),
    })

@mcp.tool()
def skill_apply(skill_id: str, task_context: str) -> str:
    """
    Apply a skill to a specific task context.
    Returns a personalised protocol combining skill steps with task context.
    """
    skills = _load_skills()
    skill = skills.get(skill_id)
    if not skill:
        return json.dumps({"ok": False, "error": f"Skill '{skill_id}' not found"})

    _log({"event": "skill_apply", "skill_id": skill_id, "ctx": task_context[:80]})
    return json.dumps({
        "ok": True,
        "skill": skill_id,
        "task_context": task_context[:200],
        "execution_plan": {
            "skill_name": skill.get("name"),
            "description": skill.get("description"),
            "steps": [f"{i+1}. {s}" for i, s in enumerate(skill.get("steps", []))],
            "tools_to_use": skill.get("tools", []),
            "anti_patterns_to_avoid": skill.get("anti_patterns", []),
            "adapted_for_task": (
                f"Apply these steps specifically to: {task_context[:100]}"
            ),
        },
    }, indent=2)

if __name__ == "__main__":
    mcp.run(transport="stdio")
