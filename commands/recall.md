# /recall — Recall from Memory

Retrieve stored memories relevant to a topic or question.

## How To Use

- `/recall` — show all memory index entries
- `/recall auth` — recall everything about auth
- `/recall user preferences` — recall my preferences
- `/recall [project name]` — recall project context

## What I'll Do

**Long-term memory** (file-based):
1. Read `~/.claude/projects/.../memory/MEMORY.md` index
2. Find relevant files by topic
3. Read and surface content

**Short-term memory** (session graph):
1. `mcp__memory__search_nodes` for the topic
2. Surface relevant entities and observations

## Memory Freshness

Memory can be stale. Before acting on recalled memory:
- File path cited → verify it exists
- Function cited → grep for it
- Decision cited → check current code

"The memory says X" ≠ "X is currently true" — verify before recommending.

## Memory Index
```
~/.claude/projects/-Users-dsr-ai-lab/memory/MEMORY.md
```
