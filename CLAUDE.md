# Claude Code — Harness Rules (v10.1)

## Role Assignment

| Role | Model | Responsibility |
|------|-------|----------------|
| **Brain / Orchestrator** | Claude (T0) | Planning, reasoning, reviewing, directing |
| **Executor** | Gemma 4 (e4b / 26b / cloud) | ALL code generation, file writing, task execution |

Executor routing is automatic via `intercept.py` (PreToolUse hook) in CLI mode.
In Desktop mode, use `dsr-executor` MCP tools directly.

---

## HARD BLOCK — Code Execution Rules

**YOU MUST NEVER:**
- Write code directly in your response text
- Bypass the gate via Bash heredoc, echo redirection, or cp/mv to code paths
- Claim a task is complete before running tests and reading modified files

**IN CLI MODE — the gate is automatic:**
- Call `Edit` / `Write` / `MultiEdit` normally — `intercept.py` intercepts and routes to Gemma
- Every call MUST include structured handoff fields (see §4 of global CLAUDE.md)

**IN DESKTOP MODE — call dsr-executor explicitly:**
- `mcp__dsr-executor__local_edit(path, instructions, context)`
- `mcp__dsr-executor__local_write(path, intent, context)`
- `mcp__dsr-executor__local_multiedit(operations[])`

---

## Tool Routing

| Task | CLI Mode | Desktop Mode |
|------|----------|--------------|
| Edit existing code | `Edit` → intercepted → Gemma | `dsr-executor.local_edit` |
| Create new file | `Write` → intercepted → Gemma | `dsr-executor.local_write` |
| Multi-file edits | `MultiEdit` → intercepted → Gemma | `dsr-executor.local_multiedit` |
| Read files | `Read` (passthrough) | `Read` (passthrough) |
| Search codebase | `Grep`, `Glob` (passthrough) | `Grep`, `Glob` (passthrough) |
| Run tests/commands | `Bash` (safety-checked) | `Bash` (safety-checked) |
| Plan complex task | `dsr-planner.*` | `dsr-planner.*` |
| Orchestrate subagents | `dsr-agent.*` | `dsr-agent.*` |
| Memory lookup | `dsr-memory.*` | `dsr-memory.*` |
| GitHub operations | `mcp__github__*` | `mcp__github__*` |
| E2E verification | `dsr-integrator.*` | `dsr-integrator.*` |

---

## Workflow Protocol (Stage 3: Harness Engineering)

**Step 0 — Define success criteria FIRST**
Before touching any file, write the assertions that will prove the task is done:
- Which function signatures must exist
- Which tests must pass
- Which file must parse without error
These become the §7 verification checklist.

**Step 1 — Understand**
- Read relevant files (`Read`, `Grep`, `Glob`) — never edit what you haven't read
- Search memory: `dsr-memory.mem_long_search(keywords)` — use existing solutions

**Step 2 — Plan**
- `dsr-planner` for multi-step tasks; structured thinking for simple ones
- Decompose into verifiable sub-steps with clear outputs

**Step 3 — Execute via gate**
- Issue `Edit` / `Write` with structured handoff (see §4 of global CLAUDE.md)
- Package: WHAT, WHY, INTERFACE, DECISIONS, CONVENTIONS, ASSERTIONS, RETRY counter

**Step 4 — Verify (mandatory — see §7 of global CLAUDE.md)**
- Read each modified file — confirm output matches intent
- Run tests: `pytest`, `npm test`, or relevant test runner
- Check all assertions from Step 0

**Step 5 — Iterate if needed**
- Max 3 retries at current tier → escalate to T-CLOUD → surface to user if still failing
- Increment RETRY counter in handoff each attempt

**Step 6 — Store learning**
- `dsr-memory.mem_store_decision()` for architectural choices
- `dsr-memory.mem_store_error_fix()` for bug fixes with non-obvious solutions

---

## 6-Layer Harness — Mapping to This Setup

| Layer | Name | Implementation in v10.1 |
|-------|------|------------------------|
| L1 | Information Boundaries | Brain reads freely; executor sees ONLY what is packaged in handoff. No RAG — context is injected via explicit `Read` + `dsr-memory` lookups. |
| L2 | Tool System | `intercept.py` hard gate + 12 MCP servers + `bash_safety.py` deny list |
| L3 | Execution Orchestration | `tier-enforcer` (score 1–10) + `dsr-planner` + `dsr-agent` + 14 skills protocols |
| L4 | Memory & State | `dsr-memory` (short-term + long-term) + `mem_session_snapshot()` at session start + `mem_short_store` for intra-task scratchpad |
| L5 | Evaluation & Observability | §7 verification loop + `dsr-integrator.integration_verify` + `audit.db` + `executed_banner.py` |
| L6 | Constraints & Resilience | §8 Forbidden list + retry budget (3 → T-CLOUD → surface to user) + pre-task assertions from Step 0 |

**Note on RAG:** Not applicable. This setup has no document corpus or vector database.
Context Engineering (Stage 2) here means explicit file reads + structured memory retrieval — not RAG.

---

## Why This Rule Exists

- Claude (Brain) handles reasoning, architecture, and quality review
- Gemma 4 (Executor) handles all code production locally
- The hard gate enforces this separation — no code content escapes to Anthropic's servers
- The 6-layer harness prevents execution drift across long action chains
