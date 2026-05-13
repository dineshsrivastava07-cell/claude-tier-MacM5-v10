# /agent — AI Agentic Task Workflow

You are in **AGENTIC MODE**. Execute complex, multi-step tasks autonomously without stopping on first failure.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([task keywords])` — check prior runs, failures
2. `tier-enforcer.classify(task_description)` → typical score 7-10 → T3/T-CLOUD
3. Use `dsr-agent.agent_decompose` to break down before execution

---

## What This Mode Does
Decomposes ambiguous tasks → researches → executes write/test/fix loop → handles failures → reports milestones → stores decisions

---

## Execution Protocol

**Step 1 — Task Decomposition** — `dsr-agent.agent_decompose`: what, which tool, success criterion, tier

**Step 2 — Research Phase** — `WebSearch`/`mcp__fetch__fetch` for docs, Read/Grep/Glob for patterns, verify APIs before assuming

**Step 3 — Execution Loop**
```
Execute → Verify → (fail) RCA → Fix → Re-verify → Continue
```
Edit/Write (→ Gemma) · Bash · `dsr-integrator.bug_fix_protocol` · `dsr-agent.agent_orchestrate`

**Step 4 — Integration** — `/wire` + `dsr-integrator.integration_verify`

**Step 5 — Verification** — Full tests · Re-check requirements · `/review` all new code

**Step 6 — Memory Store** — `dsr-memory.mem_store_decision("Agent [name]: [approach], [decisions], [what worked/failed]")`

---

## Agentic Rules
- Never stop on first failure (max 3 retries, then escalate)
- Verify after each step before moving on
- Read before writing — no blind edits
- State hypothesis before fixing
- Prefer working over perfect

---

## Post-Phase Gate
1. All steps verified · Suite passing · `/review` done · Memory updated

---

## Progress Format
```
[AGENT] Step 1/N: Decomposition ✓
[AGENT] Step N/N: Complete ✓
### Steps: N/N | Files Created: N | Modified: N | Issues Resolved: N
```
