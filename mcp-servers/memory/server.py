#!/usr/bin/env python3
"""
DSR AI-Lab · Memory MCP Server
Long-term memory: SQLite (~/.dsr-ai-lab/memory/long_term.db)
Short-term memory: in-process session dict (cleared on server restart)
FastMCP stdio. No API key. Subscription OAuth only.
"""
import json, sqlite3, time, uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

mcp = FastMCP("dsr-memory")

DB_PATH = Path.home() / ".dsr-ai-lab" / "memory" / "long_term.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Short-term: in-process session store ─────────────────────────────────────
_SHORT: dict[str, Any] = {}   # key → {value, ts, ttl_sec}

# ── Long-term: SQLite schema ──────────────────────────────────────────────────
def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS memories (
        id          TEXT PRIMARY KEY,
        category    TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT NOT NULL,
        project     TEXT DEFAULT '',
        tags        TEXT DEFAULT '',
        importance  INTEGER DEFAULT 5,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        access_count INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_category ON memories(category);
    CREATE INDEX IF NOT EXISTS idx_project  ON memories(project);
    CREATE INDEX IF NOT EXISTS idx_key      ON memories(key);
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        key, value, tags, content=memories, content_rowid=rowid
    );
    CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, key, value, tags)
        VALUES (new.rowid, new.key, new.value, new.tags);
    END;
    CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
        VALUES('delete', old.rowid, old.key, old.value, old.tags);
        INSERT INTO memories_fts(rowid, key, value, tags)
        VALUES (new.rowid, new.key, new.value, new.tags);
    END;
    """)
    return con

_db()  # initialize schema on startup

# ════════════════════════════════════════════════════════════════════════════
# SHORT-TERM MEMORY TOOLS
# ════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def mem_short_store(key: str, value: str, ttl_seconds: int = 7200) -> str:
    """
    Store a value in short-term session memory (in-process, clears on restart).
    ttl_seconds: time-to-live (default 2h). 0 = no expiry this session.
    Use for: current task context, working file list, active decisions, temp notes.
    """
    _SHORT[key] = {"value": value, "ts": time.time(), "ttl": ttl_seconds}
    return json.dumps({"ok": True, "key": key, "ttl_seconds": ttl_seconds,
                       "expires_at": datetime.fromtimestamp(
                           time.time() + ttl_seconds).isoformat() if ttl_seconds else "session_end"})

@mcp.tool()
def mem_short_get(key: str) -> str:
    """Retrieve a short-term memory value by key."""
    entry = _SHORT.get(key)
    if not entry:
        return json.dumps({"ok": False, "key": key, "error": "Not found in short-term memory"})
    if entry["ttl"] > 0 and (time.time() - entry["ts"]) > entry["ttl"]:
        del _SHORT[key]
        return json.dumps({"ok": False, "key": key, "error": "Expired"})
    return json.dumps({"ok": True, "key": key, "value": entry["value"],
                       "age_seconds": int(time.time() - entry["ts"])})

@mcp.tool()
def mem_short_list() -> str:
    """List all active short-term memory keys with age and TTL."""
    now = time.time()
    active = []
    expired = []
    for k, v in list(_SHORT.items()):
        age = int(now - v["ts"])
        if v["ttl"] > 0 and age > v["ttl"]:
            expired.append(k)
        else:
            active.append({"key": k, "age_seconds": age, "ttl": v["ttl"],
                           "preview": v["value"][:80]})
    for k in expired:
        del _SHORT[k]
    return json.dumps({"ok": True, "active": active, "expired_cleaned": expired,
                       "count": len(active)})

@mcp.tool()
def mem_short_clear(key: str = "") -> str:
    """Clear one key or all short-term memory (key='' clears all)."""
    if key:
        removed = key in _SHORT
        _SHORT.pop(key, None)
        return json.dumps({"ok": True, "cleared": key if removed else None})
    count = len(_SHORT)
    _SHORT.clear()
    return json.dumps({"ok": True, "cleared_all": True, "count": count})

# ════════════════════════════════════════════════════════════════════════════
# LONG-TERM MEMORY TOOLS
# ════════════════════════════════════════════════════════════════════════════

CATEGORIES = {
    "decision":      "Architectural or technical decision made",
    "pattern":       "Recurring code or design pattern learned",
    "error_fix":     "Error encountered and how it was fixed",
    "project":       "Project context, goals, constraints",
    "preference":    "User workflow or style preference",
    "integration":   "Integration detail, endpoint, contract",
    "rca":           "Root cause analysis outcome",
    "qa":            "QA finding or test result",
    "skill":         "Skill or capability reference",
    "note":          "General note or observation",
}

@mcp.tool()
def mem_long_store(
    key: str,
    value: str,
    category: str = "note",
    project: str = "",
    tags: str = "",
    importance: int = 5,
) -> str:
    """
    Store in long-term SQLite memory. Persists across sessions and restarts.

    category: decision|pattern|error_fix|project|preference|integration|rca|qa|skill|note
    tags: comma-separated tags for retrieval
    importance: 1 (low) to 10 (critical)

    Use for: architectural decisions, learned patterns, error→fix pairs,
             project constraints, integration contracts, RCA outcomes.
    """
    if category not in CATEGORIES:
        category = "note"
    now = datetime.utcnow().isoformat() + "Z"
    con = _db()
    # Upsert by key+project
    existing = con.execute(
        "SELECT id FROM memories WHERE key=? AND project=?", (key, project)
    ).fetchone()
    if existing:
        con.execute("""
            UPDATE memories SET value=?, category=?, tags=?, importance=?,
            updated_at=?, access_count=access_count+1
            WHERE id=?
        """, (value, category, tags, importance, now, existing["id"]))
        mem_id = existing["id"]
        action = "updated"
    else:
        mem_id = str(uuid.uuid4())[:8]
        con.execute("""
            INSERT INTO memories(id,category,key,value,project,tags,importance,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (mem_id, category, key, value, project, tags, importance, now, now))
        action = "created"
    con.commit()
    return json.dumps({"ok": True, "id": mem_id, "action": action,
                       "key": key, "category": category, "project": project})

@mcp.tool()
def mem_long_get(key: str, project: str = "") -> str:
    """Retrieve long-term memory by exact key. Increments access count."""
    con = _db()
    q = "SELECT * FROM memories WHERE key=?"
    params: list = [key]
    if project:
        q += " AND project=?"
        params.append(project)
    row = con.execute(q, params).fetchone()
    if not row:
        return json.dumps({"ok": False, "key": key, "error": "Not found in long-term memory"})
    con.execute("UPDATE memories SET access_count=access_count+1 WHERE id=?", (row["id"],))
    con.commit()
    return json.dumps({"ok": True, **dict(row)})

@mcp.tool()
def mem_long_search(
    query: str,
    category: str = "",
    project: str = "",
    limit: int = 10,
) -> str:
    """
    Full-text search long-term memory. Uses SQLite FTS5.
    query: words to search in key, value, tags.
    Filter by category and/or project.
    """
    con = _db()
    try:
        base = """
            SELECT m.* FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE memories_fts MATCH ?
        """
        params: list = [query]
        if category:
            base += " AND m.category=?"
            params.append(category)
        if project:
            base += " AND m.project=?"
            params.append(project)
        base += " ORDER BY m.importance DESC, m.access_count DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(base, params).fetchall()
    except Exception:
        # Fallback: LIKE search
        base = "SELECT * FROM memories WHERE (key LIKE ? OR value LIKE ? OR tags LIKE ?)"
        like = f"%{query}%"
        params = [like, like, like]
        if category:
            base += " AND category=?"
            params.append(category)
        if project:
            base += " AND project=?"
            params.append(project)
        base += " ORDER BY importance DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(base, params).fetchall()
    results = [dict(r) for r in rows]
    return json.dumps({"ok": True, "results": results, "count": len(results),
                       "query": query})

@mcp.tool()
def mem_long_list(category: str = "", project: str = "", limit: int = 50) -> str:
    """List long-term memories. Filter by category and/or project."""
    con = _db()
    q = "SELECT id,category,key,project,tags,importance,updated_at,access_count FROM memories WHERE 1=1"
    params: list = []
    if category:
        q += " AND category=?"
        params.append(category)
    if project:
        q += " AND project=?"
        params.append(project)
    q += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in con.execute(q, params).fetchall()]
    return json.dumps({"ok": True, "memories": rows, "count": len(rows),
                       "categories": list(CATEGORIES.keys())})

@mcp.tool()
def mem_long_delete(key: str, project: str = "") -> str:
    """Delete a long-term memory by key."""
    con = _db()
    q = "DELETE FROM memories WHERE key=?"
    params: list = [key]
    if project:
        q += " AND project=?"
        params.append(project)
    con.execute(q, params)
    con.commit()
    return json.dumps({"ok": True, "deleted_key": key})

@mcp.tool()
def mem_session_snapshot() -> str:
    """
    Dump current short-term memory + top long-term memories as a session context snapshot.
    Call at session start (after tier_gate_session_start) to restore context.
    """
    # Short-term active
    short = json.loads(mem_short_list())["active"]
    # Long-term recent + high importance
    con = _db()
    recent = [dict(r) for r in con.execute(
        "SELECT id,category,key,value,project,tags,importance FROM memories "
        "ORDER BY importance DESC, updated_at DESC LIMIT 20"
    ).fetchall()]
    return json.dumps({
        "ok": True,
        "short_term": short,
        "long_term_top20": recent,
        "snapshot_ts": datetime.utcnow().isoformat() + "Z",
        "instructions": (
            "Review short_term for current session context. "
            "Review long_term_top20 for important persistent knowledge. "
            "Use mem_long_search to find specific past decisions or patterns."
        ),
    })

@mcp.tool()
def mem_store_error_fix(
    error_signature: str,
    error_detail: str,
    fix_applied: str,
    project: str = "",
    root_cause: str = "",
) -> str:
    """
    Specialized store for error→fix pairs. Enables future RCA pattern matching.
    Automatically categorized as 'error_fix' with high importance.
    """
    value = json.dumps({
        "error": error_detail,
        "fix": fix_applied,
        "root_cause": root_cause,
    })
    return mem_long_store(
        key=error_signature,
        value=value,
        category="error_fix",
        project=project,
        tags=f"error,fix,rca",
        importance=8,
    )

@mcp.tool()
def mem_store_decision(
    decision: str,
    rationale: str,
    alternatives: str = "",
    project: str = "",
) -> str:
    """
    Store an architectural or technical decision with rationale.
    Automatically categorized as 'decision' with importance 9.
    """
    value = json.dumps({
        "decision": decision,
        "rationale": rationale,
        "alternatives_considered": alternatives,
        "recorded_at": datetime.utcnow().isoformat() + "Z",
    })
    return mem_long_store(
        key=decision[:80],
        value=value,
        category="decision",
        project=project,
        tags="decision,architecture",
        importance=9,
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
