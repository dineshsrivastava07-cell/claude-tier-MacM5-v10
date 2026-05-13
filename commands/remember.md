# /remember — Save to Long-Term Memory

Save important information from this session to long-term memory for future conversations.

## How To Use

- `/remember I prefer pytest over unittest for all Python projects`
- `/remember The auth service uses JWT with 1-hour expiry, refresh tokens in Redis`
- `/remember Use snake_case for all Python files, kebab-case for frontend components`

## Memory Types

**User preferences** → saved as `user` memory

**Project context** → saved as `project` memory

**Feedback/corrections** → saved as `feedback` memory

**External references** → saved as `reference` memory

## What I'll Do

1. Classify the memory type
2. Write to `~/.claude/projects/.../memory/[type]_[topic].md`
3. Update `MEMORY.md` index
4. Confirm: `✓ Saved: [summary]`

## What NOT to Save

- Current in-session context (use tasks instead)
- Code patterns derivable from reading the codebase
- Things already in CLAUDE.md
