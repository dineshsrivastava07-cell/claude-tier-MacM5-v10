# /arch — Architecture Design Mode

You are in **ARCHITECTURE MODE**. Design a complete, implementable system architecture with clear components, flows, contracts, and file structure.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search([system/component keywords])` — check prior architecture decisions
2. If found → apply patterns, cite entry
3. `tier-enforcer.classify(task_description)` → typical score 6-8 → T2/T3
4. Novel/enterprise-critical → T-CLOUD, state reason

---

## Tier Reference
| Score | Tier | Use When |
|---|---|---|
| 4-6 | T2 gemma4:26b | Standard component design, known patterns |
| 7-8 | T3 gemma4:26b + thinking | Complex system, novel patterns, high coupling |
| 9-10 | T-CLOUD qwen3-coder:480b | Enterprise-critical, distributed, security-sensitive |

---

## Workflow

**Step 1 — Understand Current State** — Read all relevant files first

**Step 2 — Design Components** — Name, single responsibility, inputs/outputs, tech choice, interface contract, error behavior

**Step 3 — Data & Control Flow** — ASCII diagrams for request/response, events, error paths

**Step 4 — File Structure** — Annotated directory tree

**Step 5 — Integration Points** — Connections, protocols, external deps, auth boundaries, schema changes

**Step 6 — Non-Functional Design** — Performance, reliability, security, observability

**Step 7 — Implementation Order** — Foundation → Models → Core → Integration → Tests → Polish

**Step 8 — Trade-offs** — Document every non-obvious decision

Use `mcp__sequential-thinking__sequentialthinking` for complex multi-constraint reasoning.

---

## Post-Phase Gate (MANDATORY)
- `dsr-memory.mem_store_decision("Architecture for [system]: [components], [decisions], [patterns]")`
- Present to user, get approval on interfaces before coding starts

---

## Output Format

```
## Architecture: [System/Feature Name]

### System Overview [2-3 sentences]
### Component Diagram [ASCII]
### Components [name, role, interface, tech, error behavior]
### Data Flow [ASCII — happy + error path]
### File Structure [annotated tree]
### Integration Points
### Non-Functional Design
### Key Decisions [decision table]
### Implementation Order [phases]
### Next Step → Run /plan
```
