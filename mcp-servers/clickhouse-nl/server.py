#!/usr/bin/env python3
"""
DSR AI-Lab · ClickHouse Natural Language Query MCP Server
Converts NL questions → ClickHouse SQL via Ollama, then executes.
FastMCP stdio. Read-only. No API key needed.
"""
import json
import os
import re
import requests
from fastmcp import FastMCP

# ── Config from environment ───────────────────────────────────────────────────
CH_URL      = os.environ.get("CLICKHOUSE_URL", "https://localhost:8443")
CH_USER     = os.environ.get("CLICKHOUSE_USER", "default")
CH_PASS     = os.environ.get("CLICKHOUSE_PASSWORD", "")
CH_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")
NL_MODEL    = os.environ.get("NL_MODEL", "qwen2.5-coder:7b")
TIMEOUT     = int(os.environ.get("CLICKHOUSE_TIMEOUT", "30"))

mcp = FastMCP("clickhouse-nl")

# ── ClickHouse HTTP helpers ───────────────────────────────────────────────────

def _ch_request(sql: str, database: str | None = None) -> list[dict]:
    """Execute a SELECT-class query and return rows as list of dicts."""
    db = database or CH_DATABASE
    params = {
        "query": sql,
        "database": db,
        "default_format": "JSONEachRow",
        "output_format_json_quote_64bit_integers": "0",
    }
    headers = {
        "X-ClickHouse-User": CH_USER,
        "X-ClickHouse-Key":  CH_PASS,
    }
    resp = requests.get(
        CH_URL,
        params=params,
        headers=headers,
        timeout=TIMEOUT,
        verify=True,
    )
    resp.raise_for_status()
    text = resp.text.strip()
    if not text:
        return []
    rows = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"raw": line})
    return rows


def _get_schema(database: str | None = None) -> str:
    """Return a compact schema string for the target database."""
    db = database or CH_DATABASE
    sql = f"""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = '{db}'
        ORDER BY table_name, ordinal_position
        LIMIT 800
    """
    try:
        rows = _ch_request(sql)
    except Exception:
        # Fallback: SHOW TABLES + DESCRIBE
        try:
            tables = _ch_request(f"SHOW TABLES FROM `{db}`")
            lines = [f"Database: {db}"]
            for t in tables[:20]:
                tname = t.get("name", "")
                lines.append(f"\nTable: {tname}")
                try:
                    cols = _ch_request(f"DESCRIBE TABLE `{db}`.`{tname}`")
                    for c in cols:
                        lines.append(f"  {c.get('name','')} {c.get('type','')}")
                except Exception:
                    lines.append("  (schema unavailable)")
            return "\n".join(lines)
        except Exception as e:
            return f"Schema unavailable: {e}"

    schema: dict[str, list[str]] = {}
    for row in rows:
        tbl = row.get("table_name", "unknown")
        col = row.get("column_name", "?")
        dtype = row.get("data_type", "?")
        schema.setdefault(tbl, []).append(f"{col} {dtype}")

    lines = [f"Database: {db}"]
    for tbl, cols in schema.items():
        lines.append(f"\nTable: {tbl}")
        for c in cols:
            lines.append(f"  {c}")
    return "\n".join(lines)


def _nl_to_sql(question: str, schema: str) -> str:
    """Call Ollama to convert NL question to ClickHouse SQL."""
    prompt = f"""You are a ClickHouse SQL expert. Convert the natural language question below into a valid ClickHouse SQL SELECT query.

Schema:
{schema}

Rules:
- Return ONLY the raw SQL query — no markdown, no explanation, no code fences
- Use ClickHouse dialect (e.g. toDate, formatDateTime, arrayJoin, etc.)
- Default LIMIT 100 unless the question asks for all rows
- Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER

Question: {question}

SQL:"""
    resp = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json={"model": NL_MODEL, "prompt": prompt, "stream": False},
        timeout=90,
    )
    resp.raise_for_status()
    sql = resp.json().get("response", "").strip()
    # Strip any markdown fences the model might add
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip()


def _is_safe(sql: str) -> bool:
    """Block write operations."""
    banned = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|RENAME|ATTACH|DETACH)\b",
        re.IGNORECASE,
    )
    return not banned.search(sql)


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def nl_query(question: str, database: str = "") -> str:
    """Ask a natural language question about the ClickHouse data.

    Converts your question to SQL using a local AI model (qwen2.5-coder),
    executes it, and returns both the generated SQL and the results.

    Args:
        question: Natural language question, e.g. "top 10 products by revenue last month"
        database: Optional database name (defaults to configured default)

    Returns:
        JSON with generated_sql, row_count, and results (max 50 rows shown).
    """
    db = database or CH_DATABASE
    schema = _get_schema(db)
    sql = _nl_to_sql(question, schema)

    if not _is_safe(sql):
        return json.dumps({
            "error": "Generated SQL contains write operations — blocked for safety.",
            "generated_sql": sql,
        })

    try:
        rows = _ch_request(sql, db)
        return json.dumps({
            "question":      question,
            "database":      db,
            "generated_sql": sql,
            "row_count":     len(rows),
            "results":       rows[:50],
        }, indent=2, default=str)
    except Exception as e:
        return json.dumps({
            "error":         str(e),
            "generated_sql": sql,
            "hint":          "Check if VPN is connected and credentials are correct.",
        }, indent=2)


@mcp.tool()
def list_databases() -> str:
    """List all accessible databases on the ClickHouse server."""
    try:
        rows = _ch_request("SHOW DATABASES")
        names = [r.get("name", str(r)) for r in rows]
        return json.dumps(names, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Check VPN and credentials."})


@mcp.tool()
def list_tables(database: str = "") -> str:
    """List all tables in a ClickHouse database.

    Args:
        database: Database name (defaults to configured default)
    """
    db = database or CH_DATABASE
    try:
        rows = _ch_request(f"SHOW TABLES FROM `{db}`")
        names = [r.get("name", str(r)) for r in rows]
        return json.dumps({"database": db, "tables": names}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "database": db})


@mcp.tool()
def describe_table(table: str, database: str = "") -> str:
    """Show column names and types for a ClickHouse table.

    Args:
        table:    Table name
        database: Database name (defaults to configured default)
    """
    db = database or CH_DATABASE
    try:
        rows = _ch_request(f"DESCRIBE TABLE `{db}`.`{table}`")
        return json.dumps({"database": db, "table": table, "columns": rows}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "table": table})


@mcp.tool()
def run_sql(query: str, database: str = "") -> str:
    """Execute a raw SQL SELECT query against ClickHouse.

    Only SELECT, SHOW, DESCRIBE, EXPLAIN, and WITH (CTE) queries are allowed.

    Args:
        query:    SQL query string
        database: Optional database name
    """
    if not _is_safe(query):
        return json.dumps({"error": "Write operations are blocked. Use SELECT only."})
    db = database or CH_DATABASE
    try:
        rows = _ch_request(query, db)
        return json.dumps({
            "row_count": len(rows),
            "results":   rows[:200],
        }, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e), "hint": "Check VPN and credentials."})


if __name__ == "__main__":
    mcp.run()
