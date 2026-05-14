# Claude Tier System v10.1 — MacBook Pro M5

> **Hard-Gate Hybrid AI Architecture** — Claude OAuth Brain + Local Gemma 4 Executors + Ollama Cloud T-CLOUD

[![Public](https://img.shields.io/badge/visibility-public-green)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)
[![Platform](https://img.shields.io/badge/platform-macOS%20M5-blue)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)
[![Version](https://img.shields.io/badge/version-10.1-orange)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)

---

## Changelog

### 2026-05-14 — System Audit + Harness Engineering Fixes

**Harness Engineering framework added (6-layer stack)**
- `CLAUDE.md`: project-level constitution rewritten — executor updated qwen→Gemma 4, CLI vs Desktop routing table, Step 0 workflow (define success criteria before touching files), 6-layer harness reference
- `README.md` / `ARCHITECTURE.md`: full 6-layer stack diagrams, mandatory handoff schema (WHAT/WHY/INTERFACE/DECISIONS/CONVENTIONS/ASSERTIONS/RETRY), Stage 3 paradigm explanation

**`hooks/intercept.py` — Task Assigned banner added**
- New `render_assigned_banner()` function: displays tier, model, score before each gated edit
- Updated `emit_allow_with_rewrite()` to emit banner via `additionalContext` and `/dev/tty`
- The "Task Assigned" banners visible in Claude Code output are now in sync with the repo

**Memory system fixed**
- Long-term SQLite memory (`~/.dsr-ai-lab/memory/long_term.db`) was empty — now seeded with 8 knowledge entries (user profile, system architecture, MCP servers, commands, git repo, executor rules, etc.)
- `DSR_AI_LAB_MEMORY_DB` env var corrected: `memory.db` → `memory/long_term.db`
- Stale user_profile and MCP servers reference files updated (qwen→Gemma 4, old server list replaced with actual 12 servers)
- Stale `feedback_bypass.md` (never-requested gate bypass rule) deleted from memory

**Stale hook files removed**
- Deleted `~/.claude/hooks/startup_warm_qwen.sh` — warmed wrong model (qwen2.5-coder:14b). T2 keep-alive + `session_start()` handle warmup correctly.
- Deleted `~/.claude/hooks/pre_tool_block.py` — dead v10.0 logic that redirected to `mcp__qwen_executor__*`. Active v10.1 equivalent is `hooks/intercept.py`.

**T-CLOUD clarification**
- `qwen3-coder:480b-cloud` and `gemma4:31b-cloud` are Ollama Cloud models — accessed via API, NOT pulled locally. `session_start()` "not pulled" warning is a false positive for cloud models.

---

## What Is This?

A **production-grade, local-first AI coding system** running on MacBook Pro M5 (32 GB unified memory). It routes every task to the right AI model based on complexity — automatically — while enforcing a hard gate that prevents Claude (the Brain) from directly writing code to disk.

**Brain plans. Local executes. The gate is the architecture.**

---

## Key Features

- **Hard Gate** — `intercept.py` intercepts every Edit/Write/MultiEdit tool call, classifies complexity (1–10), routes to the appropriate local Gemma 4 tier via Ollama
- **4-Tier Routing** — T1/T2/T3/T-CLOUD automatically matched to task complexity
- **T3 = Zero RAM Cost** — reuses T2 model weights with a `<|think|>` control token (no model swap, no extra memory)
- **Memory System** — long-term SQLite FTS5 memory persists decisions across sessions; compounds accuracy over time
- **12 MCP Servers** — dsr-agent, dsr-coder, dsr-planner, dsr-integrator, dsr-memory, dsr-skills, dsr-filesystem, dsr-git, tier-enforcer, github, filesystem, memory
- **18 Slash Commands** — full enterprise pipeline from `/scope` to `/release`, orchestrated by `/enterprise`
- **Enterprise Pipeline** — 10-phase delivery lifecycle with mandatory go/no-go gates at every phase
- **OAuth-Only Auth** — no `ANTHROPIC_API_KEY` anywhere; Claude authenticates via macOS Keychain
- **6-Layer Harness** — Stage 3 Harness Engineering: structured handoff schema, retry budget, pre-task assertions, intra-session scratchpad

---

## Harness Engineering — Stage 3

This system operates at **Stage 3: Harness Engineering** — not just prompt tuning or context management, but full execution scaffolding that prevents drift and catches failures across long action chains.

| Stage | Name | Goal | Limitation |
|-------|------|------|------------|
| Stage 1 | Prompt Engineering | Did the model understand me? | Hits ceiling outside model weights |
| Stage 2 | Context Engineering | Does the model have the facts? | Perfect context can't prevent execution drift |
| **Stage 3** | **Harness Engineering** | Can the model sustain correct action? | — Scaffolding prevents drift; catches and recovers from failures |

> **Note on RAG:** Context Engineering (Stage 2) in this system uses explicit `Read`/`Grep`/`Glob` + `dsr-memory` structured lookups — **not vector search**. There is no document corpus. RAG is not applicable.

### 6-Layer Stack

```
User Request
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L1: Information Boundaries (Cognitive Scope)                         │
│     Brain reads freely via Read/Grep/Glob + dsr-memory               │
│     Executor sees ONLY the structured handoff package                │
│     [WHAT · WHY · INTERFACE · DECISIONS · CONVENTIONS · ASSERTIONS]  │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L2: Tool System (Actuation)                                          │
│     Edit/Write/MultiEdit → intercept.py hard gate → Gemma executor   │
│     Bash → bash_safety.py filter                                     │
│     12 MCP servers (dsr-agent, dsr-planner, dsr-memory, ...)         │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L3: Execution Orchestration (Planning & Routing)                     │
│     tier-enforcer: score 1–10 → T1 / T2 / T3 / T-CLOUD             │
│     dsr-planner: decompose into verifiable sub-steps                 │
│     dsr-agent: multi-phase subagent orchestration                    │
│     14 skills protocols: /enterprise /scope /arch /plan ...          │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L4: Memory & State (Continuity)                                      │
│     Session start: mem_session_snapshot() — top-20 relevant memories │
│     During task: mem_short_store() — intra-session scratchpad        │
│     After task: mem_store_decision() / mem_store_error_fix()         │
│     Cross-session: SQLite FTS5 (mem_long_search)                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L5: Evaluation & Observability (Self-Awareness)                      │
│     §7 verification: Read modified files → run tests                 │
│     dsr-integrator.integration_verify() — E2E checks                │
│     audit.db: every tier routing decision logged                     │
│     executed_banner.py: PostToolUse ✓ tier · latency · fallbacks     │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ L6: Constraints, Validation & Recovery (Resilience)                  │
│     §8 Forbidden list: immutable hard rules                          │
│     Retry budget: attempt 1→2→3 at tier → T-CLOUD → surface to user │
│     Pre-task assertions (Step 0): written before work, checked after │
│     Output validation: ASSERTIONS field in every handoff             │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                        Result to User
```

### Workflow Protocol (v10.1)

| Step | Action |
|------|--------|
| **Step 0** | **Define success criteria FIRST** — write assertions before touching any file |
| Step 1 | Understand — read files, search memory (`mem_long_search`) |
| Step 2 | Plan — `dsr-planner` for complex tasks, decompose into verifiable sub-steps |
| Step 3 | Execute via gate — `Edit`/`Write` with mandatory handoff schema |
| Step 4 | Verify — read modified files, run tests, check Step 0 assertions |
| Step 5 | Iterate — max 3 retries → T-CLOUD → surface to user |
| Step 6 | Store — `mem_store_decision()` / `mem_store_error_fix()` |

### Mandatory Handoff Schema

Every executor call must include all 7 fields:

```
WHAT:        [the specific change to make — one sentence]
WHY:         [reason or constraint driving this change]
INTERFACE:   [function signatures, types, class names the output must satisfy]
DECISIONS:   [decisions from earlier in this session the executor must honor]
CONVENTIONS: [naming, style, patterns to match from existing code]
ASSERTIONS:  [conditions that must be true in the output — verified in §7]
RETRY:       [N/3 — increment on each re-issue of the same edit]
```

Omitting any field is a packaging failure. The stateless executor will guess — and guesses drift.

---

## Tier System

| Tier | Model | Score | RAM | Use When |
|------|-------|-------|-----|----------|
| **T1** | `gemma4:e4b` | 1–3 | ~4 GB | Simple scripts, config edits, trivial fixes |
| **T2** | `gemma4:26b` | 4–6 | ~20 GB | Standard features, multi-file work, integrations |
| **T3** | `gemma4:26b` + `<\|think\|>` | 7–8 | ~20 GB | Complex logic, novel patterns, architectural work |
| **T-CLOUD** | `qwen3-coder:480b-cloud` | 9–10 | Cloud | Enterprise-critical, cross-system, high-risk |
| **T-CLOUD fallback** | `gemma4:31b-cloud` | 9–10 | Cloud | Fallback when primary unavailable |

T2 is always warm. T1 loads on demand. T3 reuses T2 — no swap, no extra RAM.

---

## Repository Structure

```
claude-tier-MacM5-v10/
├── hooks/
│   ├── intercept.py          ← Hard gate: intercepts Edit/Write, routes to Gemma
│   ├── bash_safety.py        ← Blocks file-redirect bypass attempts in Bash
│   ├── pre_tool_use.py       ← PreToolUse orchestration hook
│   ├── executed_banner.py    ← PostToolUse execution banner
│   ├── session_init_hook.py  ← Session start hook
│   └── startup_banner.py     ← Startup status display
├── tier-enforcer/
│   ├── server.py             ← MCP server: classify, route, audit, health
│   └── requirements.txt
├── tier-gate/                ← Gate routing logic and audit DB
├── mcp-servers/              ← DSR MCP server implementations
├── skills-registry/          ← Skill protocol definitions
├── README.md                 ← This file
└── ARCHITECTURE.md           ← Detailed architecture + flow diagrams
```

---

## Enterprise Slash Commands

All commands live in `~/.claude/commands/`. Every command includes:
- Memory-first gate (search before solving, store after)
- Tier classification guidance
- Post-phase verification (read-back + test run)

### Phase Commands (use in order)

| Command | Purpose |
|---------|---------|
| `/scope` | Lock boundaries, constraints, dependencies before any work |
| `/arch` | Design components, interfaces, data flow, trade-offs |
| `/plan` | Phase breakdown, tier routing, risks, exit criteria |
| `/implement` | Full E2E implementation: read → execute → verify |
| `/complex` | Complex builds: 5+ files, novel architecture |
| `/wire` | Connect all layers, fix contracts, handle error propagation |
| `/integrate` | External integrations: auth, retry, circuit breaker |
| `/review` | Code review: correctness, security, perf, maintainability |
| `/qa` | Full QA: tests, coverage, regression, security scan |
| `/rca` | Root cause analysis: causal chain → proper fix → prevention |
| `/debug` | Targeted bug fix: hypothesis → fix → verify |
| `/release` | Version release with readiness gate |

### Master Pipeline

```
/enterprise
```

Chains all 10 phases with mandatory go/no-go gates. No phase skippable. No gate bypassable.

```
SCOPE → ARCH → PLAN → IMPLEMENT → WIRE → INTEGRATE → REVIEW → QA → RCA/FIX → RELEASE
  ↑                                                                        |
  └────────────────── mem_long_search → mem_store_decision ────────────────┘
```

---

## Hard Gate — How It Works

```
You type: Edit("file.py", "add feature X")
              ↓
    [PreToolUse hook: intercept.py]
              ↓
    Classify task complexity (1–10)
              ↓
    Route to tier:
      Score 1-3 → Ollama gemma4:e4b
      Score 4-6 → Ollama gemma4:26b
      Score 7-8 → Ollama gemma4:26b + <|think|>
      Score 9-10 → Ollama Cloud qwen3-coder:480b
              ↓
    Local model generates file content
              ↓
    Content written to disk
              ↓
    [PostToolUse hook: executed_banner.py]
    Reports: tier used, latency, fallbacks
```

Claude (Brain) never writes file content directly. All code generation happens locally.

---

## Safety Rules (Immutable)

- No `ANTHROPIC_API_KEY` — OAuth only via macOS Keychain
- No `.plist` / `LaunchAgent` / `LaunchDaemon` files
- No long-lived background processes
- No bash file-redirect bypass (`echo >`, `cat <<EOF`, `tee`, `sed -i` on code files)
- No self-modifying `CLAUDE.md`
- No git commit/push without explicit user instruction
- No secrets in code, files, or logs

`bash_safety.py` enforces these at the hook level.

---

## Memory System

Long-term memory persists across sessions using SQLite FTS5:

```
~/.claude/projects/-Users-dsr-ai-lab/memory/
├── MEMORY.md              ← Index (loaded every session)
├── user_profile.md        ← User role and preferences
├── feedback_*.md          ← How to collaborate
├── project_*.md           ← Active project context
└── reference_*.md         ← External system pointers
```

Every phase of every command searches memory before solving and stores decisions after. Institutional knowledge compounds across sessions.

---

## Requirements

- macOS (Apple Silicon M5)
- Claude Code CLI (OAuth authenticated)
- Ollama (`brew install ollama`)
- Models: `ollama pull gemma4:e4b && ollama pull gemma4:26b`
- Python 3.11+ (for hooks and MCP servers)
- Node.js 18+ (for some MCP servers)

---

## Setup

```bash
# 1. Clone
git clone https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10.git

# 2. Pull models
ollama pull gemma4:e4b
ollama pull gemma4:26b

# 3. Install tier-enforcer MCP
cd tier-enforcer && pip install -r requirements.txt

# 4. Configure hooks in ~/.claude/settings.json
# (see hooks/ directory for hook scripts)

# 5. Verify
claude  # session_start hook runs automatically
```

---

## License

Public repository. See individual component licenses.

---

*Brain plans. Local executes. The gate is the architecture.*
