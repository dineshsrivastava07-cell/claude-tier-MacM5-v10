# Claude Tier System v10.1 — MacBook Pro M5

> **Hard-Gate Hybrid AI Architecture** — Claude OAuth Brain + Local Gemma 4 Executors + Ollama Cloud T-CLOUD

[![Public](https://img.shields.io/badge/visibility-public-green)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)
[![Platform](https://img.shields.io/badge/platform-macOS%20M5-blue)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)
[![Version](https://img.shields.io/badge/version-10.1-orange)](https://github.com/dineshsrivastava07-cell/claude-tier-MacM5-v10)

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
