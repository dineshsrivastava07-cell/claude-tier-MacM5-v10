#!/usr/bin/env python3
"""
DSR AI-Lab · Filesystem MCP Server
Enhanced file operations: multi-file read/write, search, tree, cross-file.
FastMCP stdio. No API key. Subscription OAuth only.
"""
import fnmatch, json, os, re, shutil
from pathlib import Path
from typing import Any
from fastmcp import FastMCP

mcp = FastMCP("dsr-filesystem")

MAX_FILE_BYTES = 512_000   # 500KB hard read limit per file
MAX_MULTI     = 20         # max files in one multi-read call

def _safe_path(p: str) -> Path:
    return Path(p).expanduser().resolve()

def _read_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "error": f"Not found: {path}"}
    if not path.is_file():
        return {"ok": False, "error": f"Not a file: {path}"}
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"ok": False, "error": f"File too large ({size} bytes > {MAX_FILE_BYTES}). Use fs_read_range."}
    try:
        content = path.read_text(errors="replace")
        lines = content.splitlines()
        return {"ok": True, "path": str(path), "content": content,
                "lines": len(lines), "size": size}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mcp.tool()
def fs_read(path: str) -> str:
    """Read a single file. Returns content + line count + size."""
    return json.dumps(_read_file(_safe_path(path)))

@mcp.tool()
def fs_read_range(path: str, start_line: int, end_line: int) -> str:
    """Read a line range from a file. Lines are 1-indexed."""
    p = _safe_path(path)
    if not p.exists():
        return json.dumps({"ok": False, "error": f"Not found: {p}"})
    lines = p.read_text(errors="replace").splitlines()
    total = len(lines)
    s, e = max(0, start_line - 1), min(total, end_line)
    chunk = lines[s:e]
    return json.dumps({"ok": True, "path": str(p), "start": start_line,
                       "end": e, "total_lines": total,
                       "content": "\n".join(chunk)})

@mcp.tool()
def fs_multi_read(paths: list[str]) -> str:
    """Read up to 20 files in one call. Returns dict keyed by path."""
    if len(paths) > MAX_MULTI:
        return json.dumps({"ok": False,
                           "error": f"Too many files ({len(paths)}). Max {MAX_MULTI}."})
    results = {}
    for p in paths:
        results[p] = _read_file(_safe_path(p))
    failed = [p for p, r in results.items() if not r["ok"]]
    return json.dumps({"ok": len(failed) == 0, "results": results,
                       "failed": failed, "total": len(paths)})

@mcp.tool()
def fs_write(path: str, content: str, create_parents: bool = True) -> str:
    """Write content to file. Creates parent directories if needed."""
    p = _safe_path(path)
    if create_parents:
        p.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if p.exists():
        backup = str(p) + ".dsr-bak"
        shutil.copy2(p, backup)
    try:
        p.write_text(content)
        lines = content.count("\n") + 1
        return json.dumps({"ok": True, "path": str(p), "lines": lines,
                           "backup": backup, "size": p.stat().st_size})
    except Exception as e:
        if backup and Path(backup).exists():
            shutil.copy2(backup, p)
        return json.dumps({"ok": False, "error": str(e)})

@mcp.tool()
def fs_multi_write(writes: list[dict]) -> str:
    """
    Write multiple files atomically (best-effort).
    writes: list of {path, content} dicts.
    All writes happen or failures are reported — no partial rollback.
    """
    results = {}
    for item in writes:
        p, c = item.get("path", ""), item.get("content", "")
        if not p:
            results[p] = {"ok": False, "error": "Missing path"}
            continue
        r = json.loads(fs_write(p, c))
        results[p] = r
    failed = [p for p, r in results.items() if not r["ok"]]
    return json.dumps({"ok": len(failed) == 0, "results": results,
                       "failed": failed, "written": len(writes) - len(failed)})

@mcp.tool()
def fs_patch(path: str, old_str: str, new_str: str) -> str:
    """
    Replace exact string in file (like str_replace).
    old_str must appear exactly once. Safer than full rewrite for small edits.
    """
    p = _safe_path(path)
    if not p.exists():
        return json.dumps({"ok": False, "error": f"Not found: {p}"})
    content = p.read_text(errors="replace")
    count = content.count(old_str)
    if count == 0:
        return json.dumps({"ok": False, "error": "old_str not found in file."})
    if count > 1:
        return json.dumps({"ok": False, "error": f"old_str found {count} times — must be unique."})
    backup = str(p) + ".dsr-bak"
    shutil.copy2(p, backup)
    new_content = content.replace(old_str, new_str, 1)
    p.write_text(new_content)
    return json.dumps({"ok": True, "path": str(p), "backup": backup,
                       "lines_before": content.count("\n") + 1,
                       "lines_after": new_content.count("\n") + 1})

@mcp.tool()
def fs_delete(path: str, confirm: bool = False) -> str:
    """Delete file or empty directory. confirm must be True."""
    if not confirm:
        return json.dumps({"ok": False,
                           "error": "Set confirm=True to delete. This is irreversible."})
    p = _safe_path(path)
    if not p.exists():
        return json.dumps({"ok": False, "error": f"Not found: {p}"})
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return json.dumps({"ok": True, "deleted": str(p)})

@mcp.tool()
def fs_move(src: str, dst: str) -> str:
    """Move/rename file or directory."""
    s, d = _safe_path(src), _safe_path(dst)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return json.dumps({"ok": True, "src": str(s), "dst": str(d)})

@mcp.tool()
def fs_copy(src: str, dst: str) -> str:
    """Copy file."""
    s, d = _safe_path(src), _safe_path(dst)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(s), str(d))
    return json.dumps({"ok": True, "src": str(s), "dst": str(d)})

@mcp.tool()
def fs_tree(root: str, max_depth: int = 4, include_hidden: bool = False,
            exclude: list[str] | None = None) -> str:
    """Directory tree with file sizes. Excludes node_modules, .git, __pycache__ by default."""
    default_excludes = {"node_modules", ".git", "__pycache__", ".venv",
                        "venv", "dist", "build", ".mypy_cache", ".pytest_cache"}
    excl = default_excludes | set(exclude or [])
    root_path = _safe_path(root)

    def _walk(path: Path, depth: int) -> list[dict]:
        if depth > max_depth: return []
        items = []
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return []
        for entry in entries:
            if not include_hidden and entry.name.startswith("."): continue
            if entry.name in excl: continue
            if entry.is_dir():
                children = _walk(entry, depth + 1)
                items.append({"name": entry.name, "type": "dir",
                              "path": str(entry), "children": children})
            else:
                try:
                    size = entry.stat().st_size
                except Exception:
                    size = -1
                items.append({"name": entry.name, "type": "file",
                              "path": str(entry), "size": size})
        return items

    tree = _walk(root_path, 0)
    return json.dumps({"ok": True, "root": str(root_path),
                       "max_depth": max_depth, "tree": tree})

@mcp.tool()
def fs_search(root: str, pattern: str, file_glob: str = "*",
              max_results: int = 100, context_lines: int = 2) -> str:
    """
    Regex search across files. Returns matches with surrounding context.
    file_glob: e.g. '*.py', '*.ts', '*' for all.
    """
    root_path = _safe_path(root)
    exclude_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
    results = []
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return json.dumps({"ok": False, "error": f"Invalid regex: {e}"})

    for fpath in root_path.rglob(file_glob):
        if any(ex in fpath.parts for ex in exclude_dirs): continue
        if not fpath.is_file(): continue
        if fpath.stat().st_size > MAX_FILE_BYTES: continue
        try:
            lines = fpath.read_text(errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            if rx.search(line):
                ctx_start = max(0, i - context_lines)
                ctx_end   = min(len(lines), i + context_lines + 1)
                results.append({
                    "file": str(fpath),
                    "line": i + 1,
                    "match": line.strip(),
                    "context": lines[ctx_start:ctx_end],
                })
                if len(results) >= max_results:
                    return json.dumps({"ok": True, "results": results,
                                       "truncated": True, "count": len(results)})
    return json.dumps({"ok": True, "results": results,
                       "truncated": False, "count": len(results)})

@mcp.tool()
def fs_find(root: str, name_pattern: str = "*", file_type: str = "any",
            max_results: int = 200) -> str:
    """Find files by name pattern. file_type: file|dir|any."""
    root_path = _safe_path(root)
    exclude_dirs = {".git", "node_modules", "__pycache__", ".venv"}
    results = []
    for entry in root_path.rglob(name_pattern):
        if any(ex in entry.parts for ex in exclude_dirs): continue
        if file_type == "file" and not entry.is_file(): continue
        if file_type == "dir" and not entry.is_dir(): continue
        results.append(str(entry))
        if len(results) >= max_results: break
    return json.dumps({"ok": True, "results": results, "count": len(results)})

@mcp.tool()
def fs_stat(path: str) -> str:
    """File/directory metadata: size, mtime, permissions, line count."""
    p = _safe_path(path)
    if not p.exists():
        return json.dumps({"ok": False, "error": f"Not found: {p}"})
    st = p.stat()
    info = {"ok": True, "path": str(p), "exists": True,
            "is_file": p.is_file(), "is_dir": p.is_dir(),
            "size": st.st_size, "mtime": st.st_mtime,
            "suffix": p.suffix, "name": p.name}
    if p.is_file() and st.st_size < MAX_FILE_BYTES:
        try:
            info["lines"] = len(p.read_text(errors="replace").splitlines())
        except Exception:
            pass
    return json.dumps(info)

if __name__ == "__main__":
    mcp.run(transport="stdio")
