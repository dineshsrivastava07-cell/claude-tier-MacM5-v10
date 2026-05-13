# /rca — Root Cause Analysis

You are in **RCA MODE**. Systematically diagnose the true root cause. Never patch symptoms — find and fix the cause.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([error message keywords])` — check if seen before
2. If found → apply stored fix, cite entry
3. `tier-enforcer.classify(task_description)` → typical score 5-8 → T2/T3
4. Production incidents or data-loss → T-CLOUD

---

## Workflow

**Step 1 — Describe Symptom Precisely**
What failed · When · What changed · Reproducible? · Blast radius?

**Step 2 — Gather Evidence**
```bash
git log --oneline -20 && git diff HEAD~1
```
Read: stack trace (file:line), changed configs, all modules in call chain, CI output.

**Step 3 — Form Hypotheses** (3-5, ranked by likelihood, be specific)

**Step 4 — Investigate Each** — Grep, Read, Bash to confirm/deny each

**Step 5 — Identify Root Cause**
```
Trigger → Contributing Factor → Root Cause → Symptom
```

**Step 6 — Fix Strategy**
- Immediate: stop the bleeding
- Proper: address root cause (Edit tool → Gemma gate)
- Prevention: regression test + monitoring

**Step 7 — Implement Fix**
Read file first · Edit tool · Provide full context to executor · `dsr-integrator.bug_fix_protocol` for multi-file

**Step 8 — Verification**
```bash
pytest tests/test_specific.py -v && pytest -v --tb=short
```

**Step 9 — Prevention** — regression test + type annotation + monitoring

---

## Post-Phase Gate (MANDATORY)
1. Read fixed files · Full suite green with regression test
2. `dsr-memory.mem_store_error_fix("RCA [error]: cause=[cause], fix=[fix], prevention=[prevention]")`

---

## Output Format
```
## RCA Report: [Issue Title]
### Symptom / Timeline / Hypotheses / Investigation
### Root Cause: [Trigger] → [Factor] → [Cause] → [Symptom]
### Fix: Immediate / Proper / Prevention
### Verification: [ ] test passes [ ] suite green [ ] regression added [ ] memory stored
```
