# /plan — Structured Planning Workflow

You are in **PLANNING MODE**. Reason step by step through the user's request and produce a structured, actionable plan with tier-aware execution guidance.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([task keywords])` — check prior plans and decisions
2. If found → incorporate and cite
3. `tier-enforcer.classify(task_description)` → typical score 4-6 → T2
4. If `/scope` was run → reference stored scope definition

---

## Tier Reference
| Score | Tier | Use When |
|---|---|---|
| 1-3 | T1 gemma4:e4b | Simple scripts, config edits, trivial fixes |
| 4-6 | T2 gemma4:26b | Standard features, multi-file work |
| 7-8 | T3 gemma4:26b + thinking | Complex systems, novel patterns |
| 9-10 | T-CLOUD qwen3-coder:480b | Enterprise-critical, high-risk |

---

## Workflow

**Step 1 — Capture Intent**
- Goal in one sentence · Task type · Reference prior scope

**Step 2 — Define Scope**
- Objectives (measurable) · Deliverables · Out of scope · Constraints

**Step 3 — Phase Breakdown**
For each phase: name, tasks, tier estimate, dependencies, complexity (S/M/L/XL)

**Step 4 — Risk & Unknowns**
Top 3 risks + mitigation + escalation path

**Step 5 — Verification Plan**
Exit criteria per phase + final success criteria

**Step 6 — Execution Routing**
For each phase: which command, tier, memory checkpoints

---

## Post-Phase Gate (MANDATORY)
- `dsr-memory.mem_store_decision("Plan for [feature]: [phases], [key decisions], [risks]")`
- Present to user, get approval before Phase 1 begins

---

## Output Format

```
## Plan: [Title]

### Objective / Scope / Constraints

### Phases
#### Phase 1 — [Name] (Complexity: M | Tier: T2 | Command: /implement)
- [ ] Task 1
**Depends on:** — | **Exit criteria:** [tests pass]

### Risks
| Risk | Likelihood | Impact | Mitigation |

### Success Criteria
- [ ] All exit criteria met · Tests green · QA sign-off · Memory updated
```

After presenting: **"Shall I proceed with Phase 1, or adjust first?"**
