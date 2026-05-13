# /qa — QA Review Workflow

You are in **QA MODE**. Systematically validate correctness, coverage, and quality before any release or merge.

---

## Memory-First Gate (MANDATORY)
1. `dsr-memory.mem_long_search("QA " + component_name)` — check prior QA findings for regressions
2. `tier-enforcer.classify(task)` → typical score 4-6 → T2

---

## Pre-QA Gate
All must be true before starting QA:
- [ ] Implementation is complete (`/implement` finished)
- [ ] Wiring is complete (`/wire` finished)
- [ ] All files have been read and verified by Brain post-execution

---

## Workflow

**Step 1 — Test Inventory**
```bash
find . -name "test_*.py" -o -name "*.test.ts" -o -name "*.spec.*" | head -50
```

**Step 2 — Run Full Test Suite**
```bash
pytest -v --tb=short --cov=src --cov-report=term-missing
# or: npm test -- --coverage
# or: cargo test
# or: go test ./...
```

**Step 3 — Coverage Analysis**
- Zero-coverage paths?
- Error paths tested?
- Boundary conditions covered?
- Use `dsr-integrator.qa_review`

**Step 4 — Code Quality Review**
Use `dsr-coder.code_review_checklist`: correctness, security, performance, maintainability

**Step 5 — Integration Validation**
- `dsr-integrator.integration_verify`
- Test failure scenarios: timeout, auth failure, malformed response, rate limit

**Step 6 — Regression Check**
```bash
git stash && pytest tests/ && git stash pop && pytest tests/
```

**Step 7 — Security Scan**
```bash
bandit -r src/ -ll  # Python
npm audit           # JS/TS
govulncheck ./...   # Go
```
BLOCK on HIGH severity.

**Step 8 — QA Sign-off Checklist**
- [ ] All tests pass (0 failures)
- [ ] Coverage meets threshold (≥ 80%)
- [ ] No HIGH security issues
- [ ] No regressions
- [ ] E2E verified
- [ ] Error paths tested
- [ ] Performance within bounds

---

## Post-Phase Gate (MANDATORY)
- PASS: `dsr-memory.mem_store_decision("QA PASS [component] v[version]: [key findings]")`
- FAIL: `dsr-memory.mem_store_error_fix("QA FAIL [component]: [issues found]")`
- BLOCK `/release` if checklist has any unchecked items

---

## Output Format

```
## QA Report: [Component/Feature] v[version]

### Test Results
| Suite | Pass | Fail | Skip | Coverage |
|---|---|---|---|---|

### Failures
[None — or list each with file:line and root cause]

### Coverage Gaps
- path/to/file.py: lines N-M (handler uncovered)

### Code Quality Issues
| Severity | Issue | File:Line | Action |
|---|---|---|---|

### Security Findings
| Severity | Issue | File:Line | Action |
|---|---|---|---|

### QA Sign-off
[ ] PASS — all checks green, ready for /release
[ ] FAIL — N issues must be resolved, then re-run /qa
```
