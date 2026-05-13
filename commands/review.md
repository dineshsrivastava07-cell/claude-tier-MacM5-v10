# /review — Code Review

You are in **CODE REVIEW MODE**. Thorough, structured review for correctness, security, performance, and maintainability.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([component] + "review")` — check prior findings
2. `tier-enforcer.classify(task_description)` → typical score 4-6 → T2
3. Use `dsr-coder.code_review_checklist`

---

## How to Invoke
- `/review` — files modified in this session
- `/review src/auth.py` — specific file
- `/review for security` — security focus only

---

## Review Dimensions

**1. Correctness** — edge cases, null/empty/max, return values, error conditions, matches spec

**2. Security** — no SQL/command injection, no XSS, no hardcoded secrets, input validated at boundaries, proper auth/authz, no sensitive data in logs

**3. Performance** — no N+1, appropriate data structures, no blocking in async, resources released, no unbounded growth

**4. Maintainability** — clear naming, no magic numbers, single responsibility, consistent with codebase, dead code removed

**5. Error Handling** — caught at right layer, meaningful messages, no swallowed exceptions, proper logging

**6. Tests** — testable, happy + error paths, edge cases, deterministic, no duplicated logic

**7. Observability** — logging at boundaries, appropriate levels, no sensitive data in logs

---

## Post-Review Gate (MANDATORY)
- Issues found: `dsr-memory.mem_store_error_fix("Review [component]: [issue] → [fix]")`
- Clean: `dsr-memory.mem_store_decision("Review PASS [component]: clean")`
- HIGH → block merge, trigger `/debug` or `/rca`

---

## Output Format
```
## Code Review: [filename]
### Correctness / Security / Performance / Maintainability / Error Handling / Tests / Observability
### Summary: Must fix (HIGH): N | Should fix (MED): N | Consider (LOW): N | Overall: PASS/FAIL
→ Fix HIGH via /debug, or PASS — proceed to /qa
```
