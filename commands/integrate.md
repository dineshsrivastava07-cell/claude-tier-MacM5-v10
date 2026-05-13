# /integrate — E2E Integration Workflow

You are in **E2E INTEGRATION MODE**. Wire, test, and validate a complete integration between systems or services.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([system A] + [system B] + "integration")` — check prior attempts and gotchas
2. `tier-enforcer.classify(task_description)` → typical score 5-8 → T2/T3

---

## Workflow

**Step 1 — Integration Specification**
Define before touching code: System A outputs, System B inputs, protocol, auth, data format, error scenarios.

**Step 2 — Research**
`WebSearch` / `mcp__fetch__fetch` for SDK docs, auth, rate limits, pagination, known bugs.

**Step 3 — Build Integration Layer** (Edit/Write → Gemma gate)
1. Auth/credentials (env vars only — never hardcode)
2. Client/SDK init with connection pooling
3. Request builder with input validation
4. Response parser with schema validation
5. Retry (exponential backoff)
6. Timeout handling
7. Circuit breaker (if critical path)

Read back each file after writing.

**Step 4 — Wire Into Application**
Register with DI, startup sequence, health check, internal service layer.

**Step 5 — Integration Tests**
```bash
pytest tests/integration/ -v --tb=short
```
Cover: happy path, auth failure (401), timeout/retry, malformed response, rate limit (429).

**Step 6 — E2E Validation** — `dsr-integrator.integration_verify`

**Step 7 — Observability**
Request log + error log + metrics (requests, errors, latency_ms)

---

## Post-Phase Gate (MANDATORY)
1. Files verified · Integration tests green · E2E confirmed
2. `dsr-memory.mem_store_decision("Integration [A↔B]: [protocol], [auth], [retry], [gotchas]")`

---

## Output Format
```
## Integration Complete: [A ↔ B]
### Contract / Files Created / Test Results / E2E Verification / Observability
→ Run /qa before release
```
