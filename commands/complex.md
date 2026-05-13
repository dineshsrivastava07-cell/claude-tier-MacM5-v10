# /complex — Complex Multi-Step Coding

You are in **COMPLEX CODING MODE**. Handle large, multi-component tasks requiring careful orchestration across many files.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([task/system keywords])` — check prior decisions
2. `tier-enforcer.classify(task_description)` → typical score 7-10 → T3/T-CLOUD
3. Default T3; escalate T-CLOUD for novel/enterprise-critical

---

## When to Use
5+ files, 3+ distinct components, MCP server, API, CLI tool, agent system, novel architecture

---

## Workflow

**Step 1 — Pre-Analysis (NEVER SKIP)** — Read ALL relevant code, use `dsr-coder.code_cross_file_deps`

**Step 2 — Design Before Coding** — Components, data models (first), interfaces, implementation order, tier per component. Get confirmation before proceeding.

**Step 3 — Scaffold** — `dsr-coder.code_scaffold` for structure

**Step 4 — Foundation** — Models → utilities → core logic (Edit/Write → Gemma, read back each)

**Step 5 — Features** — Service → API/CLI → Integration adapters

**Step 6 — Wire** — `/wire` protocol

**Step 7 — Test**
```bash
pytest -v --tb=short --cov=src/new_module
```

**Step 8 — Review (NEVER SKIP)** — `dsr-coder.code_review_checklist` + `/review` per file

---

## Complexity Rules
- T1-T2: use `/implement` instead
- T3 (7-8): complex multi-component, novel patterns
- T-CLOUD (9-10): enterprise-critical, distributed, AI architecture

---

## Post-Phase Gate (MANDATORY)
1. All files read back · Full suite green · `/review` on each major component
2. `dsr-memory.mem_store_decision("Complex build [system]: [components], [patterns], [decisions], [gotchas]")`

---

## Progress Format
```
[COMPLEX] Step 1/8: Pre-analysis ✓
[COMPLEX] Step 2/8: Design confirmed ✓
...
[COMPLEX] Complete ✓
→ Run /qa then /release
```
