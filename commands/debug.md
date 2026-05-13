# /debug — Debug Session

You are in **DEBUG MODE**. Systematically diagnose and fix a specific bug. For systemic failures, use `/rca`.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([error keywords])` — check if seen and fixed before
2. If found → apply stored fix, cite entry
3. `tier-enforcer.classify(task_description)` → typical score 2-5 → T1/T2

---

## Workflow

**Step 1 — Capture Error Precisely** — exact message, file:line, reproducible?, last working state

**Step 2 — Read Failing Code** — exact line, data passed, unexpected state, upstream caller

**Step 3 — Form Hypothesis**
> "I believe the bug is X because Y, as evidenced by Z"
Do not skip. Blind edits create new bugs.

**Step 4 — Fix**
- Read file (if not done in Step 2)
- Edit tool (gated → Gemma): broken code + error + expected behavior + context
- Keep fix minimal — fix the bug, do not refactor

**Step 5 — Verify**
```bash
pytest tests/test_specific.py::test_name -v && pytest -v --tb=short
```

**Step 6 — Root Cause Note**
> "Bug was [X] because [Y] — fixed by [Z]"

---

## Post-Phase Gate (MANDATORY)
1. Read fixed file · Specific test passes · No regressions
2. `dsr-memory.mem_store_error_fix("[error]: [cause] → fixed by [fix]")`

---

## Common Patterns
| Error | First Place to Look |
|---|---|
| AttributeError/TypeError | None returned, type mismatch, missing field |
| ImportError | Missing package, wrong path, circular import |
| KeyError | Missing config, env var not set |
| ConnectionError | Service down, wrong port, pool exhausted |
| Flaky/intermittent | Race condition, test order dependency, timing |

For systemic failures → `/rca`
