#!/usr/bin/env python3
"""
DSR AI-Lab · Agent MCP Server
Intelligent agentic orchestration, subagent management, task decomposition.
FastMCP stdio. No API key. Subscription OAuth only.
"""
import json, uuid, time
from datetime import datetime
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

mcp = FastMCP("dsr-agent")

LOG_PATH = Path.home() / ".dsr-ai-lab" / "agent" / "agent.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# In-process agent registry — tracks active tasks and subagents this session
_AGENTS: dict[str, dict] = {}
_TASKS:  dict[str, dict] = {}

def _log(e: dict) -> None:
    e["ts"] = datetime.utcnow().isoformat() + "Z"
    with open(LOG_PATH, "a") as f: f.write(json.dumps(e) + "\n")

# ── Task Decomposition ────────────────────────────────────────────────────────

@mcp.tool()
def agent_decompose(
    goal: str,
    context: str = "",
    max_subtasks: int = 12,
    decomposition_strategy: str = "sequential",
) -> str:
    """
    Intelligently decompose a complex goal into ordered, executable subtasks.
    Each subtask has: tier assignment, tool chain, acceptance criterion, dependencies.

    decomposition_strategy:
      sequential  — each subtask must complete before next starts
      parallel    — identify subtasks that can run concurrently
      pipeline    — output of each subtask feeds into next

    Claude uses this to plan agentic execution before touching any file or tool.
    """
    task_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat() + "Z"

    # Build decomposition framework
    # Claude fills in actual subtasks based on the goal — this is the protocol
    decomposition = {
        "task_id": task_id,
        "goal": goal,
        "strategy": decomposition_strategy,
        "created_at": now,
        "protocol": [
            "STEP 1: Analyse goal for ambiguity — clarify before decomposing",
            "STEP 2: Identify the smallest verifiable units of work",
            "STEP 3: Assign each subtask a tier (T1/T2/T3) via tier_gate_classify",
            "STEP 4: Identify dependencies between subtasks",
            "STEP 5: Order subtasks — dependencies first, parallelisable tasks grouped",
            "STEP 6: Define acceptance criterion for each subtask",
            "STEP 7: Identify which subtasks need human confirmation before execution",
        ],
        "subtask_template": {
            "id": "ST-001",
            "description": "What to do",
            "tier": "T1|T2|T3",
            "tools_required": ["list of MCP tools needed"],
            "inputs": ["what this subtask needs as input"],
            "outputs": ["what this subtask produces"],
            "acceptance_criterion": "How to verify this subtask succeeded",
            "depends_on": ["ST-000"],
            "requires_human_confirmation": False,
            "estimated_complexity": "LOW|MEDIUM|HIGH",
        },
        "max_subtasks": max_subtasks,
        "ground_rules": [
            "Each subtask is atomic — one clear action, one verifiable outcome",
            "No subtask executes before its dependencies complete",
            "Subtasks requiring irreversible actions need requires_human_confirmation=True",
            "T3 subtasks are orchestrators — they call T1/T2 via tier gate",
            "Store completed subtask results in mem_short_store key=ST-{id}",
        ],
    }

    _TASKS[task_id] = {"goal": goal, "status": "DECOMPOSING", "subtasks": [],
                       "created_at": now}
    _log({"event": "agent_decompose", "task_id": task_id, "goal": goal[:80]})
    return json.dumps(decomposition, indent=2)

# ── Subagent Spawning ─────────────────────────────────────────────────────────

@mcp.tool()
def agent_spawn_subagent(
    parent_task_id: str,
    subtask_id: str,
    subtask_description: str,
    tier: str,
    tools_available: list[str],
    context: str = "",
    inputs: dict | None = None,
) -> str:
    """
    Spawn a subagent for a specific subtask. Registers it in the agent registry.
    The subagent operates within strict boundaries: only its declared tools, only its subtask.

    tier: T1|T2|T3
    tools_available: list of MCP tool names the subagent may use

    For T1/T2 subagents: Claude calls tier_gate_run_t1/t2 with the scoped prompt.
    For T3 subagents: Claude itself executes with bounded scope.
    """
    agent_id = f"SA-{str(uuid.uuid4())[:6]}"
    now = datetime.utcnow().isoformat() + "Z"

    # Build the scoped subagent definition
    subagent = {
        "agent_id": agent_id,
        "parent_task_id": parent_task_id,
        "subtask_id": subtask_id,
        "description": subtask_description,
        "tier": tier,
        "status": "READY",
        "created_at": now,
        "scope": {
            "allowed_tools": tools_available,
            "context": context[:500],
            "inputs": inputs or {},
            "boundaries": [
                "Only use tools in allowed_tools list",
                "Only operate on files/paths specified in inputs",
                "Do not expand scope beyond subtask_description",
                "Report back structured output — do not apply results autonomously",
            ],
        },
        "execution_protocol": {
            "T1": f"Call tier_gate_run_t1 with task_description='{subtask_description}' "
                  "and a fully self-contained prompt. Review output before reporting.",
            "T2": f"Call tier_gate_run_t2 with task_description='{subtask_description}' "
                  "and a fully self-contained prompt. Review output before reporting.",
            "T3": "Execute directly. Apply full accuracy protocol. "
                  "Stay within scope boundaries. Report structured output.",
        }.get(tier, "Call tier gate to classify first"),
        "output_schema": {
            "agent_id": agent_id,
            "subtask_id": subtask_id,
            "status": "COMPLETE|FAILED|BLOCKED",
            "outputs": {},
            "errors": [],
            "escalation_needed": False,
        },
    }

    _AGENTS[agent_id] = subagent
    if parent_task_id in _TASKS:
        _TASKS[parent_task_id]["subtasks"].append(agent_id)

    _log({"event": "spawn_subagent", "agent_id": agent_id,
          "tier": tier, "subtask": subtask_id})
    return json.dumps(subagent, indent=2)

# ── Orchestration ─────────────────────────────────────────────────────────────

@mcp.tool()
def agent_orchestrate(
    task_id: str,
    subtasks: list[dict],
    stop_on_failure: bool = True,
) -> str:
    """
    Orchestrate execution of a decomposed task's subtasks.
    Manages dependency resolution, sequential/parallel grouping, and failure handling.

    subtasks: ordered list from agent_decompose output.
    Returns execution plan with dependency-resolved order.

    Claude follows this plan — calling agent_spawn_subagent for each subtask in order.
    """
    if not subtasks:
        return json.dumps({"ok": False, "error": "No subtasks provided"})

    # Resolve dependency order (topological sort)
    id_map = {st.get("id"): st for st in subtasks}
    resolved = []
    visited  = set()

    def _visit(st_id: str):
        if st_id in visited: return
        visited.add(st_id)
        for dep in id_map.get(st_id, {}).get("depends_on", []):
            if dep in id_map: _visit(dep)
        if st_id in id_map:
            resolved.append(id_map[st_id])

    for st in subtasks:
        _visit(st.get("id", ""))

    # Group into sequential waves (subtasks with same dependency level can be parallel)
    waves = []
    completed = set()
    remaining = list(resolved)
    max_iterations = len(remaining) + 5

    for _ in range(max_iterations):
        if not remaining: break
        wave = [st for st in remaining
                if all(d in completed for d in st.get("depends_on", []))]
        if not wave:
            # Circular dependency or unresolvable
            waves.append({"wave": len(waves) + 1, "parallel": False,
                          "subtasks": remaining,
                          "note": "DEPENDENCY_ERROR: circular or missing dep"})
            break
        waves.append({"wave": len(waves) + 1,
                      "parallel": len(wave) > 1,
                      "subtasks": wave})
        for st in wave:
            completed.add(st.get("id"))
            remaining.remove(st)

    plan = {
        "ok": True,
        "task_id": task_id,
        "total_subtasks": len(subtasks),
        "execution_waves": waves,
        "stop_on_failure": stop_on_failure,
        "execution_protocol": [
            "Execute each wave in order",
            "Within a wave: parallel=True means subtasks may run concurrently (spawn multiple subagents)",
            "Within a wave: parallel=False means strictly sequential",
            "After each wave: verify all subtasks in wave completed successfully",
            "On any FAILED subtask: if stop_on_failure=True, halt and report",
            "Store wave completion in mem_short_store key=wave_{n}_complete",
            "On completion of all waves: call qa_review for overall verification",
        ],
        "failure_protocol": [
            "Capture exact error and context",
            "Call rca_analyze to identify root cause",
            "Attempt fix if root cause is clear and fix is small",
            "Escalate to user if fix is unclear or scope-expanding",
            "Never silently swallow a subtask failure",
        ],
    }

    _log({"event": "orchestrate", "task_id": task_id, "waves": len(waves)})
    return json.dumps(plan, indent=2)

# ── Agent Status ──────────────────────────────────────────────────────────────

@mcp.tool()
def agent_status(task_id: str = "") -> str:
    """
    Report status of all agents or a specific task's agents.
    Use to check progress during long-running orchestration.
    """
    if task_id and task_id in _TASKS:
        task = _TASKS[task_id]
        agents = {aid: _AGENTS.get(aid, {}) for aid in task.get("subtasks", [])}
        return json.dumps({"ok": True, "task": task, "subagents": agents})

    return json.dumps({
        "ok": True,
        "active_tasks": {tid: {
            "goal": t["goal"][:60], "status": t["status"],
            "subtask_count": len(t.get("subtasks", [])),
        } for tid, t in _TASKS.items()},
        "active_agents": {aid: {
            "subtask": a.get("subtask_id"),
            "tier": a.get("tier"),
            "status": a.get("status"),
        } for aid, a in _AGENTS.items()},
    })

# ── Intelligent Implementation Agent ─────────────────────────────────────────

@mcp.tool()
def agent_implement(
    task: str,
    files: list[str],
    language: str,
    complexity: str = "HIGH",
    context: str = "",
) -> str:
    """
    Full intelligent implementation agent protocol.
    Combines: scope → decompose → plan → spawn subagents → orchestrate → qa.

    This is the master protocol for end-to-end implementation tasks.
    Claude follows this as its operating procedure for complex tasks.
    """
    task_id = str(uuid.uuid4())[:8]
    _log({"event": "agent_implement", "task_id": task_id, "task": task[:80]})

    return json.dumps({
        "ok": True,
        "task_id": task_id,
        "task": task,
        "master_protocol": [
            {"phase": "ANALYSE",
             "tools": ["plan_scope_analysis", "mem_session_snapshot"],
             "action": "Understand full scope, load memory context, identify risks"},
            {"phase": "READ",
             "tools": ["fs_multi_read", "code_cross_file_deps"],
             "action": f"Read all {len(files)} files. Map dependency graph. No coding yet."},
            {"phase": "PLAN",
             "tools": ["plan_architecture", "plan_phases", "plan_todos"],
             "action": "Create architecture doc, phase plan, ordered TODO list"},
            {"phase": "DECOMPOSE",
             "tools": ["agent_decompose"],
             "action": "Break implementation into atomic subtasks with tier assignments"},
            {"phase": "ORCHESTRATE",
             "tools": ["agent_spawn_subagent", "agent_orchestrate",
                       "tier_gate_classify", "tier_gate_run_t1", "tier_gate_run_t2"],
             "action": "Execute subtasks in dependency order via tier-gated subagents"},
            {"phase": "INTEGRATE",
             "tools": ["code_cross_file_deps", "integration_verify"],
             "action": "Verify all files work together. Check all integration points."},
            {"phase": "QA",
             "tools": ["qa_review", "code_review_checklist"],
             "action": "Full QA pass. Fix all CRITICAL and HIGH findings."},
            {"phase": "RCA_CHECK",
             "tools": ["rca_analyze", "bug_fix_protocol"],
             "action": "If any failures: root cause analysis before any fix attempt"},
            {"phase": "MEMORY",
             "tools": ["mem_store_decision", "mem_store_error_fix", "mem_long_store"],
             "action": "Persist decisions, patterns, and error→fix pairs to long-term memory"},
            {"phase": "REPORT",
             "tools": [],
             "action": "Structured completion report: what was done, what changed, what was learned"},
        ],
        "ground_rules": [
            "ANALYSE and READ phases are non-skippable regardless of urgency",
            "Never code before completing READ phase",
            "Every subagent operates within declared scope only",
            "Every failure triggers RCA before retry",
            "Long-term memory is updated on every significant decision",
        ],
        "files_in_scope": files,
        "language": language,
        "complexity": complexity,
    }, indent=2)

if __name__ == "__main__":
    mcp.run(transport="stdio")
