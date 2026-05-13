# Architecture — Claude Tier System v10.1

> MacBook Pro M5 · Hard-Gate Hybrid · Brain (Claude OAuth) + Local Gemma 4 Executors

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CLAUDE TIER SYSTEM v10.1                            │
│                     MacBook Pro M5 · 32 GB Unified Memory               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                   T0 — BRAIN (Claude OAuth)                     │   │
│   │          api.anthropic.com · Claude Sonnet 4.6 / Opus 4.x      │   │
│   │    Plans · Decides · Orchestrates · Reviews · Verifies          │   │
│   └──────────────────────────┬──────────────────────────────────────┘   │
│                              │ Tool calls                               │
│                              ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              HARD GATE (hooks/intercept.py)                     │   │
│   │   PreToolUse hook intercepts Edit / Write / MultiEdit           │   │
│   │   Classifies complexity score 1–10                              │   │
│   │   Routes to appropriate local tier via Ollama                   │   │
│   └──────┬──────────┬──────────────┬──────────────────────────────--┘   │
│          │          │              │                                     │
│          ▼          ▼              ▼                                     │
│   ┌────────┐  ┌──────────┐  ┌──────────┐   ┌─────────────────────┐     │
│   │   T1   │  │    T2    │  │    T3    │   │      T-CLOUD        │     │
│   │Score   │  │ Score    │  │ Score    │   │    Score 9–10        │     │
│   │  1–3   │  │  4–6     │  │  7–8    │   │                     │     │
│   │gemma4  │  │gemma4    │  │gemma4   │   │  qwen3-coder:480b   │     │
│   │ :e4b   │  │  :26b    │  │  :26b   │   │  (Ollama Cloud)     │     │
│   │~4 GB   │  │ ~20 GB   │  │ ~20 GB  │   │  + <|think|> token  │     │
│   │on-demand│ │  warm    │  │warm+    │   │  fallback:          │     │
│   └────────┘  └──────────┘  │thinking │   │  gemma4:31b-cloud   │     │
│                              └──────────┘   └─────────────────────┘     │
│                                                                         │
│   localhost:11434 (Ollama)                   Ollama Cloud API           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Hard Gate — Detailed Flow

Every file write passes through this gate. No exceptions.

```
Claude Brain emits: Edit("src/app.py", new_string="...")
                          │
                          ▼
              ┌─────────────────────┐
              │  PreToolUse Hook    │
              │  (intercept.py)     │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  tier-enforcer MCP  │
              │  classify(task)     │
              │  → score: 1–10      │
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┬──────────────┐
          │              │              │              │
       score 1-3      score 4-6      score 7-8      score 9-10
          │              │              │              │
          ▼              ▼              ▼              ▼
    Ollama T1      Ollama T2      Ollama T3      Ollama Cloud
    gemma4:e4b    gemma4:26b    gemma4:26b      qwen3-coder
                               + <|think|>       :480b-cloud
          │              │              │              │
          └──────────────┴──────────────┴──────────────┘
                                  │
                                  ▼
                    Local model generates content
                    (Brain's intent → actual code)
                                  │
                                  ▼
                         Written to disk
                                  │
                                  ▼
              ┌─────────────────────┐
              │  PostToolUse Hook   │
              │  executed_banner.py │
              │  Reports: tier,     │
              │  latency, fallbacks │
              └─────────────────────┘
```

**Key property:** Claude Brain provides *intent* ("add null check at line 42"). The local model generates the *actual content*. Claude never sees or produces the file bytes.

---

## T3 — Zero Cost Thinking Mode

T3 is not a separate model. It is T2 with a control token:

```
T2:  system_prompt = ""
T3:  system_prompt = "<|think|>"

Same weights. Same loaded RAM (~20 GB).
No model swap. No extra memory.
8-character difference activates chain-of-thought reasoning.
```

This means T3 is always available when T2 is warm — at zero additional cost.

---

## Bash Safety Gate

A second PreToolUse hook (`bash_safety.py`) blocks bypass attempts:

```
Blocked patterns:
  echo "..." > file.py          ← output redirect
  cat <<EOF > file.py ... EOF   ← heredoc redirect
  tee file.py < input           ← tee redirect
  sed -i 's/.../.../' file.py   ← in-place sed on code
  python -c "open('f','w')..."  ← inline Python write
  cp src dst (to code paths)    ← file copy bypass

These would allow Brain to write code without going through the gate.
bash_safety.py detects and blocks all of them.
```

---

## MCP Server Architecture

12 MCP servers provide specialized capabilities:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Server Layer                             │
├──────────────────────┬──────────────────────────────────────────┤
│  DSR Custom Servers  │           Standard Servers              │
├──────────────────────┼──────────────────────────────────────────┤
│  dsr-agent           │  github     — GitHub API operations      │
│    agent_decompose   │  filesystem — File system access         │
│    agent_orchestrate │  memory     — Knowledge graph memory     │
│    agent_spawn       │  fetch      — Web fetch                  │
│                      │  sequential-thinking — Step reasoning    │
│  dsr-coder           │  puppeteer  — Browser automation         │
│    code_scaffold     │  clickhouse-cloud — DB operations        │
│    code_multi_file   │  MCP_DOCKER — Docker integration         │
│    code_cross_deps   │                                          │
│    code_review       │                                          │
│    code_implement    │                                          │
│                      │                                          │
│  dsr-planner         │                                          │
│    plan_scope        │                                          │
│    plan_architecture │                                          │
│    plan_phases       │                                          │
│    plan_todos        │                                          │
│    plan_deep_review  │                                          │
│                      │                                          │
│  dsr-integrator      │                                          │
│    integration_verify│                                          │
│    qa_review         │                                          │
│    bug_fix_protocol  │                                          │
│    rca_analyze       │                                          │
│    fix_issues_from_qa│                                          │
│                      │                                          │
│  dsr-memory          │                                          │
│    mem_long_search   │                                          │
│    mem_long_store    │                                          │
│    mem_store_decision│                                          │
│    mem_store_error   │                                          │
│    mem_session_snap  │                                          │
│                      │                                          │
│  dsr-skills          │                                          │
│    skill_lookup      │                                          │
│    skill_apply       │                                          │
│    skill_get         │                                          │
│                      │                                          │
│  dsr-filesystem      │                                          │
│  dsr-git             │                                          │
│  tier-enforcer       │                                          │
│    session_start     │                                          │
│    classify          │                                          │
│    tier_health       │                                          │
│    audit_summary     │                                          │
└──────────────────────┴──────────────────────────────────────────┘
```

---

## Hook System

Three hooks fire on every Claude Code tool use:

```
Session Start
    │
    ▼
session_init_hook.py ──→ startup_banner.py
    (SessionStart)            Displays tier status, model health,
                              MCP server count, skills registry

Any Tool Use
    │
    ▼
pre_tool_use.py ──────→ [Route by tool type]
    (PreToolUse)              Edit/Write/MultiEdit → intercept.py (GATE)
                              Bash → bash_safety.py (SAFETY CHECK)
                              Read/Grep/Glob → passthrough
                              MCP tools → passthrough

After Tool Use
    │
    ▼
executed_banner.py ───→ [Display execution result]
    (PostToolUse)             ✓ Tool · Tier · Latency · Fallbacks
                              ✗ Tool · Tier · [N fallback(s)]
```

---

## Memory Architecture

```
~/.claude/projects/-Users-dsr-ai-lab/memory/
├── MEMORY.md                    ← Index (loaded every session, max 200 lines)
│
├── user/
│   └── user_profile.md          ← Role, expertise, preferences
│
├── feedback/
│   ├── feedback_bypass.md       ← User can ask to skip gate
│   └── feedback_qwen_executor.md← Gemma 4 is current executor (v10.1)
│
├── project/
│   ├── project_dsr_deepagent.md ← Current system context
│   └── project_vscode_setup.md  ← VS Code + Claude Code setup
│
└── reference/
    ├── reference_mcp_servers.md  ← All MCP server locations
    ├── reference_commands.md     ← All /commands and purposes
    └── reference_git_repo.md     ← This repo: claude-tier-MacM5-v10

Long-term memory: SQLite FTS5 at ~/.dsr-ai-lab/memory.db
  - mem_long_search() — full-text search across all stored decisions
  - mem_store_decision() — persist architectural decisions
  - mem_store_error_fix() — persist bug fixes and RCA results
  - mem_session_snapshot() — load top-20 relevant memories at session start
```

**Memory compounds across sessions.** Every decision stored is available to every future session. The system gets smarter with use.

---

## Enterprise Pipeline — Phase Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│              /enterprise — Master Pipeline                          │
│                                                                     │
│  Phase 0    /scope      ──→ Scope sign-off gate                    │
│     │                                                               │
│     ▼                                                               │
│  Phase 1    /arch       ──→ Architecture approval gate             │
│     │                                                               │
│     ▼                                                               │
│  Phase 2    /plan       ──→ Plan approval gate                     │
│     │                                                               │
│     ▼                                                               │
│  Phase 3    /implement  ──→ All files verified + tests green        │
│          or /complex    ──→ (5+ files or novel architecture)        │
│     │                                                               │
│     ▼                                                               │
│  Phase 4    /wire       ──→ Smoke test + E2E verification           │
│     │                                                               │
│     ▼                                                               │
│  Phase 5    /integrate  ──→ Integration tests pass (all scenarios)  │
│     │                                                               │
│     ▼                                                               │
│  Phase 6    /review     ──→ Zero HIGH severity issues               │
│     │                                                               │
│     ▼                                                               │
│  Phase 7    /qa         ──→ QA sign-off checklist fully checked     │
│     │                                                               │
│     ▼                                                               │
│  Phase 8    /rca        ──→ Root cause found, fix applied,          │
│          or /debug           regression test added                  │
│     │         │                                                     │
│     │         └──────────────────────────── loop back to Phase 7   │
│     ▼                                                               │
│  Phase 9    /release    ──→ Tag created, smoke test passed          │
│                                                                     │
│  Memory gate at EVERY phase:                                        │
│    BEFORE: mem_long_search([keywords])                              │
│    AFTER:  mem_store_decision([summary])                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tier Routing Decision Tree

```
New task arrives
      │
      ▼
tier-enforcer.classify(task_description)
      │
      ├── Score 1-3 ──→ T1: gemma4:e4b
      │                  Simple scripts, config, trivial fixes
      │                  Load on demand (~4 GB, ~10-30s warmup)
      │
      ├── Score 4-6 ──→ T2: gemma4:26b
      │                  Standard features, CRUD, multi-file work
      │                  Always warm (~20 GB loaded)
      │
      ├── Score 7-8 ──→ T3: gemma4:26b + <|think|>
      │                  Complex logic, novel patterns, arch work
      │                  No extra RAM (reuses T2), thinking activated
      │
      └── Score 9-10 ──→ T-CLOUD: qwen3-coder:480b-cloud
                         Enterprise-critical, distributed systems
                         → fallback: gemma4:31b-cloud (if primary unavailable)
                         Cloud inference via Ollama Cloud API
```

---

## Data Flow — Single Edit Operation

```
User request: "Add retry logic to the API client"
      │
      ▼
Claude Brain (T0)
  1. mem_long_search("retry logic API client")      ← check memory
  2. Read src/api_client.py                          ← understand current code
  3. Plan the change                                 ← reasoning
  4. Emit: Edit("src/api_client.py", instructions)  ← delegate
      │
      ▼
intercept.py (PreToolUse hook)
  1. Extract file path + instructions
  2. classify("edit src/api_client.py: add retry")  → score: 6
  3. Route to T2 (gemma4:26b)
  4. POST /v1/messages → localhost:11434
      │
      ▼
Ollama T2 (gemma4:26b)
  1. Receives: intent + file context
  2. Generates: correct code with retry logic
  3. Returns: new file content
      │
      ▼
intercept.py
  1. Writes generated content to disk
  2. Returns success to Claude Code runtime
      │
      ▼
executed_banner.py (PostToolUse hook)
  └── Displays: ✓ Edit · T2 · gemma4:26b · 45s
      │
      ▼
Claude Brain (T0)
  1. Read src/api_client.py                          ← verify output
  2. Run tests via Bash                              ← confirm green
  3. mem_store_decision("Added retry to api_client") ← persist
```

---

## Security Model

```
Trust boundaries:

  api.anthropic.com          ← Claude Brain (reasoning only, no file access)
        │
        │ OAuth token (macOS Keychain)
        │ No ANTHROPIC_API_KEY
        │
  Claude Code runtime
        │
        ├── Read/Grep/Glob   → direct filesystem access (read-only)
        ├── Bash             → filtered by bash_safety.py
        └── Edit/Write       → intercepted by intercept.py
                                    │
                              localhost:11434
                              (Ollama — local, air-gapped for code gen)
                                    │
                              Generated content → disk

  No code content leaves the machine (except T-CLOUD tasks → Ollama Cloud).
  No API keys stored in files.
  No secrets in logs.
  Authentication: OAuth only.
```

---

## Component Health at Session Start

Every session runs `tier-enforcer.session_start()` which checks:

```
✓ Claude OAuth           — Keychain entry found
✓ Ollama daemon          — UP at localhost:11434
✓ T1 model (gemma4:e4b)  — pulled
✓ T2 model (gemma4:26b)  — pulled + warming
✓ T-CLOUD primary        — qwen3-coder:480b-cloud (pulled/not pulled)
✓ T-CLOUD fallback       — gemma4:31b-cloud (pulled/not pulled)
✓ Audit DB               — N routing entries
✓ Hooks                  — 3 hooks present
✓ Skills registry        — N skill protocols
✓ MCP servers            — N servers configured
```

If status = DEGRADED → user is informed. Pipeline does not proceed silently.

---

## File Path Map

```
~/.claude/
├── settings.json              ← MCP servers, hooks configuration
├── CLAUDE.md                  ← System constitution (this architecture)
├── commands/                  ← 18 slash command protocols
│   ├── enterprise.md          ← Master pipeline orchestrator
│   ├── scope.md / arch.md / plan.md
│   ├── implement.md / complex.md / wire.md
│   ├── integrate.md / review.md / qa.md
│   ├── rca.md / debug.md / release.md
│   ├── agent.md / multi-edit.md / cross-edit.md
│   └── remember.md / recall.md
└── projects/-Users-dsr-ai-lab/
    └── memory/                ← Persistent memory files

~/.dsr-ai-lab/
├── audit.db                   ← SQLite tier routing audit log
└── memory.db                  ← SQLite FTS5 long-term memory

~/claude-tier-MacM5-v10/       ← This repository (on GitHub)
├── hooks/                     ← Hook scripts
├── tier-enforcer/             ← MCP classifier server
├── tier-gate/                 ← Gate routing logic
├── mcp-servers/               ← DSR MCP implementations
└── skills-registry/           ← Skill protocol definitions
```

---

*Brain plans. Local executes. The gate is the architecture.*
