# 001 — Drift check verdict

Verdict: PASS

## Task-by-task

### Task 1 — Failing tests
- [✅] All 8 new test functions present
- [✅] Assertions match plan exactly where quoted
- Notes: All 8 functions (`test_chinese_paren_city`, `test_chinese_paren_city_district`, `test_base_prefix_city`, `test_bare_city_at_start`, `test_english_paren_does_not_match`, `test_database_does_not_trigger_base_prefix`, `test_bare_scan_leftmost_city_wins`, `test_unknown_native_city_in_brackets_yields_none_district`) present verbatim. Commit SHA: f6a6ccb.

### Task 2 — _build_location helper + drop district fallback
- [✅] Helper function present at the right location (inserted after `_REMOTE_TOKENS_EN`, before `parse_location`)
- [✅] Bracket-path delegates to helper via `_build_location(city_native, district, work_mode)`
- [✅] Old "stuff native form into district" fallback removed (the `district=city_native` line is gone)
- Notes: Commit SHA: ea34b6c. The `_REMOTE_TOKENS_CN` check inside `_build_location` correctly handles the remote-Chinese-bracket case that was previously in the bracket path body.

### Task 3 — Paren probe
- [✅] `_RE_PAREN` regex with restrictive CJK content class `[一-鿿]{2,4}(?:·[一-鿿]{2,6})?` exactly as prescribed
- [✅] Wired into `parse_location` after bracket miss (`if m is None: m = _RE_PAREN.search(s)`)
- Notes: Commit SHA: c4e544c. Probe order is correct: bracket tried first, paren only on bracket miss.

### Task 4 — base-prefix probe
- [✅] `_RE_BASE_PREFIX` with `(?<![A-Za-z])` lookbehind and `re.IGNORECASE` present
- [✅] Wired after paren (separate `if m is None` block after bracket+paren resolution)
- Notes: Commit SHA: 6c14cde. Regex placed immediately below `_RE_PAREN` as prescribed.

### Task 5 — bare-scan
- [✅] `_scan_bare_city` present, iterates `_CITY_PINYIN`, returns leftmost by string position
- [✅] Wired last (after base-prefix, before final `return Location(work_mode=work_mode)`)
- Notes: Commit SHA: 89714a3. Docstring matches plan exactly. Leftmost-wins logic uses `pos < best_pos` comparison.

### Task 6 — verification
- [✅] `uv run pytest tests/domain` green (60 passed, 0 failed)
- [✅] `uv run ruff check .` green (all checks passed)
- Notes: No Task-6 commit expected (verification only). All 12 location tests pass (5 original + 7 new pattern/guard tests; `test_bare_scan_leftmost_city_wins` makes 8 new but `test_no_brackets_no_city` was already there for 5 original).

## Scope creep findings

Minor: `normalize.py` includes ruff-style reformatting of the `parse_salary` section and `_try_annual_cny`/`_try_monthly_k` helpers (trailing-comma style, line-length unfolding). These changes are entirely in the salary domain — no semantic effect, no test changes — and were not called out by the plan. Likely applied by `ruff format` run during Task 6 verification. This is cosmetic only and does not affect correctness or the location domain.

No files outside `src/jma/domain/normalize.py` and `tests/domain/test_normalize_location.py` were modified.

## Missing-scope findings

None. All 8 test functions are present. All 4 probe paths are wired in `parse_location` in the prescribed order (bracket → paren → base-prefix → bare-scan). Unknown-city behavior is fixed in the bracket path via `_build_location` and is not re-introduced by the new probes.

## Final commit SHAs vs plan-prescribed commit messages

| SHA     | Actual subject                                                          | Plan-prescribed message                                                        | Match? |
|---------|-------------------------------------------------------------------------|--------------------------------------------------------------------------------|--------|
| f6a6ccb | test(domain): cover paren/base-prefix/bare-city location patterns (#6)  | test(domain): cover paren/base-prefix/bare-city location patterns (#6)         | ✅ exact |
| ea34b6c | refactor(domain): extract _build_location, drop district fallback (#6)  | refactor(domain): extract _build_location, drop district fallback (#6)         | ✅ exact |
| c4e544c | feat(domain): parse_location handles （city） and （city·district） parens (#6) | feat(domain): parse_location handles （city） and （city·district） parens (#6) | ✅ exact |
| 6c14cde | feat(domain): parse_location handles 'base \<city\>' prefix (#6)        | feat(domain): parse_location handles 'base \<city\>' prefix (#6)               | ✅ exact |
| 89714a3 | feat(domain): parse_location bare-city fallback scan, leftmost wins (#6) | feat(domain): parse_location bare-city fallback scan, leftmost wins (#6)       | ✅ exact |
