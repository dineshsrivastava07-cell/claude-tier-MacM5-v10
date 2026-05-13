# /release — Version Release Workflow

You are in **RELEASE MODE**. Execute a safe, fully verified, traceable version release.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search("release " + project_name)` — check prior release issues
2. `tier-enforcer.classify(task)` → typical score 2-4 → T1/T2

---

## Pre-Release Gate (ALL must be GREEN)
- [ ] `/qa` completed and PASSED
- [ ] All tests pass on release branch
- [ ] No open HIGH-severity RCA items
- [ ] No uncommitted changes
- [ ] Changelog entry written
- [ ] Version string updated

If ANY unchecked → STOP.

---

## Workflow

**Step 1 — Release Readiness Audit**
```bash
git status
git log --oneline -15
git diff main...HEAD --stat
```

**Step 2 — Version Bump** (SemVer: MAJOR.MINOR.PATCH)
- MAJOR: breaking change
- MINOR: new feature, backwards compatible
- PATCH: bug fix only

Update: `pyproject.toml` / `package.json` / `Cargo.toml` / `go.mod`

**Step 3 — Changelog Entry**
```
## v{version} — {date}
### Added / Fixed / Breaking Changes / Migration Notes
```

**Step 4 — Final Green Build**
```bash
pytest -v  # must be 0 failures
```
STOP if any failure.

**Step 5 — Tag & Release**
```bash
git add -A
git commit -m "chore: release v{version}"
git tag -a v{version} -m "Release v{version}: {summary}"
```

**Step 6 — Post-Release Verification**
- Verify tag visible
- Smoke test in target environment
- Check startup logs
- Verify version endpoint

**Step 7 — Communicate**
- Update docs if API changed
- Close resolved GitHub issues

---

## Post-Phase Gate (MANDATORY)
- `dsr-memory.mem_store_decision("Released v{version} of {project}: {key changes}, {date}")`

---

## Output Format

```
## Release: v{version} — {project}

### Pre-Release Gate
✓ QA passed | ✓ Tests green | ✓ No RCA blockers | ✓ Changelog updated

### Release Artifacts
- Tag: v{version} · Commit: {sha} · Branch: {branch}

### Post-Release Verification
✓ Smoke test passed · ✓ Version confirmed · ✓ No startup errors
```
