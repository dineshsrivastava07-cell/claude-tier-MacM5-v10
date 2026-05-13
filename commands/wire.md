# /wire — End-to-End Wiring

You are in **E2E WIRING MODE**. Connect all layers from entry point to storage, ensuring data flows correctly end-to-end.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([feature] + "wiring")` — check prior wiring patterns
2. `tier-enforcer.classify(task_description)` → typical score 4-6 → T2

---

## What Wiring Means
- Route → Controller → Service → Repository → Database
- CLI → Handler → Engine → Output
- Event → Listener → Processor → Side Effect

---

## Workflow

**Step 1 — Map the Full Stack**
Read all layer files. Draw complete flow with data shapes at each boundary.
Use `dsr-coder.code_cross_file_deps` to auto-map dependencies.

**Step 2 — Identify Gaps**
Missing imports, mismatched contracts, unhandled error propagation, missing DI registrations

**Step 3 — Wire Each Connection**
For each gap (Edit tool → Gemma gate):
- Add imports, register routes/handlers
- Transform data at boundary mismatches
- Add error handling at layer boundaries
- Read back after each edit

**Step 4 — Config & Environment**
Env vars → config → components. Secrets from env only. Init order correct.

**Step 5 — Smoke Test**
```bash
pytest tests/test_e2e.py -v
```
Fail → `dsr-integrator.bug_fix_protocol`

**Step 6 — Integration Verify**
`dsr-integrator.integration_verify` — full flow with real data

---

## Post-Phase Gate (MANDATORY)
1. Files verified · Smoke test passes · E2E confirmed
2. `dsr-memory.mem_store_decision("Wiring [feature]: [layers], [patterns], [gotchas]")`

---

## Output Format
```
## Wiring Complete: [Feature]
### Flow: [Entry] → [L1] → [L2] → [Output]
### Gaps Fixed / Smoke Test ✓ / Next Step → /qa
```
