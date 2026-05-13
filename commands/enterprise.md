# /enterprise — Enterprise-Grade Full Pipeline

You are in **ENTERPRISE PIPELINE MODE**. Execute the complete, end-to-end software delivery lifecycle with mandatory quality gates, memory integration, and tier-aware execution at every phase.

This is the master orchestrator. It chains all phase commands with verification gates between each. No phase may be skipped. No gate may be bypassed.

---

## Pipeline Overview

```
MEMORY CHECK → SCOPE → ARCH → PLAN → IMPLEMENT → WIRE → INTEGRATE → REVIEW → QA → RCA/FIX → RELEASE
      ↑                                                                              |
      └──────────────── mem_long_search at each phase ──── mem_store_decision ───────┘
```

---

## System Health Check (MANDATORY FIRST STEP)
Before any work begins:
1. `tier-enforcer.session_start()` — verify Ollama, models loaded, classifier ready
2. If DEGRADED → inform user, do not proceed silently
3. `dsr-memory.mem_session_snapshot()` — load all relevant memory for this task
4. `dsr-memory.mem_long_search([task keywords])` — check for prior work on this feature/system

---

## Phase 0 — Scope (`/scope`)
**Gate in:** User has described the task
**Execute:** `/scope` protocol — define boundaries, constraints, dependencies, risks
**Gate out:** User confirms scope sign-off checklist
**Memory:** `mem_store_decision("Scope [feature]: in=[...], out=[...], constraints=[...]")`
**Tier:** T1-T2 (score 2-5)

❌ **BLOCK** if scope is ambiguous. Resolve before proceeding.

---

## Phase 1 — Architecture (`/arch`)
**Gate in:** Scope is signed off
**Execute:** `/arch` protocol — components, interfaces, data flow, file structure, trade-offs
**Gate out:** Architecture presented and approved by user before coding begins
**Memory:** `mem_store_decision("Architecture [feature]: [components], [key decisions]")`
**Tier:** T2-T3 (score 6-8); T-CLOUD for novel/distributed/enterprise-critical systems

❌ **BLOCK** if architecture has unresolved interface conflicts.

---

## Phase 2 — Planning (`/plan`)
**Gate in:** Architecture approved
**Execute:** `/plan` protocol — phased breakdown, tier assignments, risks, exit criteria per phase
**Gate out:** Plan presented and approved; explicit "proceed" from user
**Memory:** `mem_store_decision("Plan [feature]: [phases], [risks], [tier routing]")`
**Tier:** T2 (score 4-6)

❌ **BLOCK** if any phase has undefined exit criteria.

---

## Phase 3 — Implementation (`/implement` or `/complex`)
**Gate in:** Plan approved; all files to be touched have been Read
**Execute:**
- Use `/implement` for standard features (T2-T3)
- Use `/complex` for 5+ file systems or novel architecture (T3-T-CLOUD)
- One file at a time: Edit/Write (gated → Gemma) → Read back → verify → continue
**Gate out:** All files implemented and verified; tests pass
**Memory:** `mem_store_decision("Implemented [feature]: [patterns used], [gotchas]")`
**Tier:** T2 (4-6) standard / T3 (7-8) complex / T-CLOUD (9-10) enterprise-critical

❌ **BLOCK** if any file fails post-write read verification.
❌ **BLOCK** if tests fail — use `/debug` or `/rca` before proceeding.

---

## Phase 4 — Wiring (`/wire`)
**Gate in:** All components implemented and individually verified
**Execute:** `/wire` protocol — connect all layers, fix contracts, handle error propagation
**Gate out:** Smoke test passes; E2E flow confirmed with `dsr-integrator.integration_verify`
**Memory:** `mem_store_decision("Wiring [feature]: [connections made], [patterns]")`
**Tier:** T2 (score 4-6)

❌ **BLOCK** if smoke test fails. Debug before proceeding.

---

## Phase 5 — Integration (`/integrate`)
**Gate in:** Wiring complete and smoke-tested
**Execute:** `/integrate` protocol — external service integration, auth, retry, circuit breaker, observability
**Gate out:** Integration tests pass (happy path + all failure scenarios)
**Memory:** `mem_store_decision("Integration [A↔B]: [protocol], [auth], [retry], [gotchas]")`
**Tier:** T2-T3 (score 5-8)

❌ **BLOCK** if any failure scenario test fails.

---

## Phase 6 — Code Review (`/review`)
**Gate in:** All implementation, wiring, and integration complete
**Execute:** `/review` protocol on every new/modified file
**Gate out:** Zero HIGH severity issues; all MEDIUM issues addressed or explicitly deferred
**Memory:** `mem_store_error_fix("Review findings [component]: [issues] → [fixes]")` for any issues found
**Tier:** T2-T3 (score 4-8)

❌ **BLOCK** on any HIGH severity finding (security, correctness, data loss risk).

---

## Phase 7 — QA (`/qa`)
**Gate in:** Code review passed
**Execute:** `/qa` protocol — full test suite, coverage, integration validation, regression check, security scan
**Gate out:** QA sign-off checklist fully checked
**Memory:** `mem_store_decision("QA PASS [feature] v[version]: [coverage], [key findings]")`
**Tier:** T2 (score 4-6)

❌ **BLOCK** on any unchecked sign-off item. Fix and re-run `/qa`.

---

## Phase 8 — RCA & Bug Fix (if needed) (`/rca` + `/debug`)
**Trigger:** Any test failure, review finding, or QA block at Phases 3-7
**Execute:**
- `/rca` for systemic failures (causal chain analysis, prevention)
- `/debug` for isolated bugs (targeted fix)
**Gate out:** Failing test now passes; regression test added; root cause stored in memory
**Memory:** `mem_store_error_fix("[error]: root cause=[cause], fix=[fix], prevention=[prevention]")`
**Tier:** T2-T3 (score 5-8)

After fixing → **return to Phase 7** (re-run QA, do not skip).

---

## Phase 9 — Release (`/release`)
**Gate in:** QA sign-off obtained; all phases green
**Execute:** `/release` protocol — readiness audit, version bump, changelog, final test run, tag, post-release verification
**Gate out:** Tag created, smoke test passes in target environment, version confirmed
**Memory:** `mem_store_decision("Released v[version] of [project]: [changes], released [date]")`
**Tier:** T1-T2 (score 2-4)

❌ **BLOCK** if any pre-release gate item is unchecked.

---

## Tier Gate Summary
| Phase | Typical Score | Tier |
|---|---|---|
| Scope | 2-5 | T1/T2 |
| Architecture | 6-8 | T2/T3 |
| Planning | 4-6 | T2 |
| Implementation (standard) | 5-7 | T2/T3 |
| Implementation (complex) | 8-10 | T3/T-CLOUD |
| Wiring | 4-6 | T2 |
| Integration | 5-8 | T2/T3 |
| Review | 5-8 | T2/T3 |
| QA | 4-6 | T2 |
| RCA | 5-8 | T2/T3 |
| Release | 2-4 | T1/T2 |

Trust the classifier. Do NOT override unless you have an explicit, stated reason.

---

## Memory Protocol (applies to every phase)
**Before each phase:**
- `dsr-memory.mem_long_search([phase + component keywords])`
- Apply any found decisions; cite the entry

**After each phase:**
- `dsr-memory.mem_store_decision(...)` — what was decided and why
- `dsr-memory.mem_store_error_fix(...)` — any errors encountered and how resolved

Memory is institutional knowledge. Every session compounds the next.

---

## Enterprise Quality Standards
- ✓ Read before every Edit — no blind writes
- ✓ Read back after every Edit — verify executor output
- ✓ Tests green before advancing any phase gate
- ✓ Security reviewed — no injection, no secrets, auth boundaries correct
- ✓ Memory updated — decisions and fixes persisted
- ✓ No phase skipped — even under time pressure, gates exist for a reason

---

## Invocation
- `/enterprise` — run full pipeline for the current task
- `/enterprise scope` — run only the scope phase
- `/enterprise from phase 3` — resume pipeline from implementation
- `/enterprise review qa release` — run only the final three phases

---

## Pipeline Status Board

```
Phase 0  Scope          [ ] pending / [✓] done / [✗] blocked
Phase 1  Architecture   [ ] pending / [✓] done / [✗] blocked
Phase 2  Planning       [ ] pending / [✓] done / [✗] blocked
Phase 3  Implementation [ ] pending / [✓] done / [✗] blocked
Phase 4  Wiring         [ ] pending / [✓] done / [✗] blocked
Phase 5  Integration    [ ] pending / [✓] done / [✗] blocked
Phase 6  Review         [ ] pending / [✓] done / [✗] blocked
Phase 7  QA             [ ] pending / [✓] done / [✗] blocked
Phase 8  RCA/Fix        [ ] N/A     / [✓] done / [✗] blocked
Phase 9  Release        [ ] pending / [✓] done / [✗] blocked

Overall: [ ] In Progress — blocked at Phase N: [reason]
         [✓] Complete — v[version] released
```
