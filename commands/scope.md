# /scope — Scope Analysis Workflow

You are in **SCOPE MODE**. Define and lock scope before any architecture, planning, or coding begins. Ambiguous scope is the #1 cause of rework.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([feature/area keywords])` — check prior scope decisions for this area
2. If found → apply stored constraints and cite the memory entry
3. `tier-enforcer.classify(task_description)` → typical score 2-5 → T1/T2

---

## Workflow

**Step 1 — Capture Raw Intent**
- Restate the user's goal in one precise sentence
- Classify task type: `feature` / `bug fix` / `refactor` / `integration` / `architecture` / `investigation` / `release`
- Identify who requested this and why (business driver)

**Step 2 — Boundary Analysis**
Define explicitly:
- **In scope:** concrete deliverables (files, APIs, behaviors, services)
- **Out of scope:** adjacent work explicitly excluded — name it so it can't creep in
- **Deferred:** work that belongs to a future iteration
- **Assumptions:** things taken as true without verification

**Step 3 — Stakeholder & Constraint Mapping**
- Who consumes this output? (other teams, services, users)
- Tech constraints: existing stack, dependency versions, language targets
- Non-functional requirements: latency, throughput, availability, security
- Compliance or legal constraints

**Step 4 — Dependency Audit**
- What must exist before this work starts?
- What does this work block (downstream consumers)?
- External services, APIs, or data sources required
- Internal modules that will be touched or affected

**Step 5 — Scope Risk Assessment**
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|----------|
| Scope creep at [boundary] | H/M/L | H/M/L | Explicit exclusion documented |
| Ambiguity in [requirement] | H/M/L | H/M/L | Ask user to clarify before proceeding |
| Hidden dependency on [system] | H/M/L | H/M/L | Audit in Step 4 |

**Step 6 — Sign-off Checklist**
Do NOT proceed to `/arch` or `/plan` until all are checked:
- [ ] Goal is unambiguous and agreed
- [ ] Out of scope is explicitly named
- [ ] All upstream dependencies identified
- [ ] All downstream consumers identified
- [ ] Non-functional requirements stated
- [ ] Scope risks documented

---

## Post-Phase Gate (MANDATORY)
- Store scope: `dsr-memory.mem_store_decision("Scope for [feature]: [summary of in/out/constraints]")`
- Block next phase until user confirms sign-off checklist

---

## Output Format

```
## Scope: [Feature/Task Name]

### Goal
[One sentence — what is being built and why]

### Task Type
[feature / bug fix / refactor / integration / architecture / investigation / release]

### In Scope
- ...

### Out of Scope
- ...

### Deferred
- ...

### Assumptions
- ...

### Dependencies
| Dependency | Type | Status | Owner |
|---|---|---|---|

### Constraints
- Tech: ...
- Performance: ...
- Security: ...

### Scope Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|

### Sign-off
- [ ] Scope confirmed by user
- [ ] Ready to proceed to /arch or /plan
```

After presenting scope, ask: **"Is this scope correct? Any additions or exclusions before I proceed to architecture/planning?"**
