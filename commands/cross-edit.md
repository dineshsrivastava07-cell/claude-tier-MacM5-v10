# /cross-edit — Cross-File Edit with Dependency Tracking

You are in **CROSS-FILE EDIT MODE**. Changes spanning many files with strict dependency tracking and zero broken references.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([old name] + "rename/refactor")` — check prior cross-file changes
2. `tier-enforcer.classify(task_description)` → typical score 5-7 → T2/T3
3. `dsr-coder.code_cross_file_deps` — auto-map all deps before starting

---

## Use When
Renaming functions/classes/variables · Changing API contracts · Pattern migration · Refactoring shared utilities · Data model field propagation

---

## Workflow

**Step 1 — Discovery (ALL references)**
```bash
grep -rn "old_name" src/ tests/ config/ docs/ --include="*.{py,ts,json,yaml,md}"
```
Report: **"N references across M files"** — list all before touching any.

**Step 2 — Impact Analysis** — Definition / Direct usage / Indirect / Test / Config / Dynamic (flag these!)

**Step 3 — Change Specification** — Document every location before touching any
```
src/models/user.py:15  — rename OldName → NewName (definition)
src/services/auth.py:8 — update import
```

**Step 4 — Execute in Order** — Definitions → Direct → Indirect → Tests → Config/Docs
Read · Edit (full context including "files already updated: [list]") · Read back · ✓

**Step 5 — Consistency Verification**
```bash
grep -rn "old_name" src/ --include="*.py"  # must be 0
pytest -v --tb=short
python -c "import src.main"  # no circular imports
```

**Step 6 — Dynamic Reference Audit**
```bash
grep -rn '"old_name"\|'"'"'old_name'"'"'' src/  # string literals
grep -rn "getattr.*old" src/  # reflection
```

---

## Post-Phase Gate
1. Zero grep hits · Suite green · No circular imports · Dynamic refs clean
2. `dsr-memory.mem_store_decision("Cross-edit [old→new]: [N files], [order], [dynamic refs found]")`

---

## Output Format
```
## Cross-Edit Complete: [Change]
### Discovery: N refs in M files
### Changes Applied: ✓ per file
### Verification: grep=0 · tests pass · no circular · dynamic clean
→ Run /review then /qa
```
