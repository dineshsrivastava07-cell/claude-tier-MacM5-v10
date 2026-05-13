# /implement — Full Implementation Workflow

You are in **IMPLEMENTATION MODE**. Execute a complete, verified, end-to-end implementation.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([feature/component keywords])` — check prior decisions and patterns
2. `tier-enforcer.classify(task_description)` → typical score 5-8 → T2/T3

---

## Tier Reference
| Score | Tier | Use When |
|---|---|---|
| 4-6 | T2 gemma4:26b | Standard features, CRUD, known patterns |
| 7-8 | T3 gemma4:26b + thinking | Complex logic, multi-system, new patterns |
| 9-10 | T-CLOUD qwen3-coder:480b | Enterprise-critical, novel architecture |

---

## Pre-Implementation Gate
- [ ] `/scope` done · [ ] `/arch` approved · [ ] `/plan` defined · [ ] Files Read

---

## Workflow

**Step 1 — Pre-Implementation Read**
Read ALL files to be touched. Understand: naming, error handling, import ordering, test patterns.

**Step 2 — Declare Implementation Plan**
Files to create (new) + files to modify + order (leaf deps first) + interface contracts

**Step 3 — Execute (one file at a time)**
- `Edit` for existing files (gated → Gemma)
- `Write` for new files (gated → Gemma)
- Provide clear intent + full context — executor is stateless
- **Read back** after each file to verify before moving on

**Step 4 — Wire Together**
Imports, registrations, DI, config, error propagation, startup order

**Step 5 — Test**
```bash
pytest -v --tb=short
```

**Step 6 — Code Review**
`dsr-coder.code_review_checklist`: correctness, security, edge cases, style

**Step 7 — Verify E2E**
`dsr-integrator.integration_verify` — entry point through to final output

---

## Execution Rules
- Read before Edit — always
- One file at a time — implement, verify, move on
- Never inline code — all generation through Edit/Write gate
- If step fails → `dsr-integrator.bug_fix_protocol` before retrying

---

## Post-Phase Gate (MANDATORY)
1. Read each modified file — verify output
2. Run full test suite — must be green
3. `dsr-memory.mem_store_decision("Implemented [feature]: [patterns], [decisions], [gotchas]")`

---

## Reporting

After each file: `✓ [filename] — [what was done]`

After completion:
```
## Implementation Complete
### Files Created / Modified / Test Results / How to Test / Next Steps
→ Run /qa for full quality review
```
