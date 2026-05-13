# /multi-edit — Multi-File Editing Workflow

You are in **MULTI-FILE EDIT MODE**. Coordinate changes across multiple files safely, consistently, in correct dependency order.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([change keywords])` — check prior multi-file edits
2. `tier-enforcer.classify(task_description)` → typical score 5-7 → T2/T3

---

## Workflow

**Step 1 — Map All Affected Files** — List every file, what changes and why, dependency order, risk level

**Step 2 — Read All Files** — Before editing any. Note structure, what changes, dependencies, risks.

**Step 3 — Change Plan Table**
| # | File | Change Type | Description | Depends On | Risk |
|---|------|------------|-------------|------------|------|

**Step 4 — Execute in Dependency Order**
1. Foundation/types first · 2. Implementation · 3. Wiring/DI · 4. Config · 5. Tests last

For each: Edit tool (→ Gemma) with full context · Read back · Mark ✓

**Step 5 — Cross-File Consistency**
Imports consistent · Signatures match · Config keys consistent · Grep for orphaned refs · `dsr-coder.code_cross_file_deps`

**Step 6 — Test**
```bash
pytest -v --tb=short
```

---

## Rules
- Read before Edit — every file, no exceptions
- Pass context — executor is stateless, include interface contracts
- One file at a time with verification
- High-risk files last

---

## Post-Phase Gate
1. All files verified · Suite green · Consistency confirmed
2. `dsr-memory.mem_store_decision("Multi-edit [change]: [files], [order], [pattern]")`

---

## Progress
```
[ ] 1. models.py — add field X
[✓] 2. repository.py — use field X
```
