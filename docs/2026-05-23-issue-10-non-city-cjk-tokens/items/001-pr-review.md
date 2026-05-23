# 001 — PR Review (post-fix re-review, 2026-05-23)

Verdict: PASS

PR: https://github.com/snowshine0216/job-market-agent/pull/17
Branch: `claude/issue-10-first-known-city-001`
Fix commits: `77da306` (test), `8e48d67` (fix), `fde5784` (ADR update)

---

## Prior finding status

### P0 — RESOLVED: multiple bracket/paren spans, only first was excised

**Commit:** `8e48d67`

The old `str.replace(captured, ' ', 1)` per-probe approach is gone. The new
code in `parse_location` (lines 347–349 of `normalize.py`) runs:

```python
bare_scan_input = s
for pattern in (_RE_BRACKET, _RE_PAREN, _RE_BASE_PREFIX):
    bare_scan_input = re.sub(pattern, " ", bare_scan_input)
```

This globally excises every span matched by each shape pattern before
bare-scan runs, not only the first span captured by the probe loop.

Live verification (commands run by this reviewer):

```
parse_location("【高级】工程师【北京路】招聘")  → city=None  ✓
parse_location("（高级）测试（北京路）招聘")     → city=None  ✓
```

Five new regression tests added in `77da306` all pass:
- `test_multiple_brackets_only_first_captured_all_excised_before_bare_scan`
- `test_two_non_city_brackets_with_shanghai_street_excised`
- `test_bracket_plus_paren_both_non_city_remainder_bare_scan_finds_city`
- `test_two_parens_only_first_captured_both_excised`
- `test_existing_paren_excision_regression_guard`

### P1 (latent code-smell) — RESOLVED: loop variable `text` shadowing

**Commit:** `8e48d67`

The `for text in excised_texts:` loop and the `excised_texts` list are
completely gone. The new approach has no loop variable that could shadow the
`text` parameter. The variable shadowing defect cannot recur.

### P1 (pre-existing) — OPEN: progressive-prefix resolves street-name substrings

`parse_location("base 北京路工程师") → city=Beijing` still occurs. Pre-existing,
out of scope for this PR. Follow-up issue should be filed to add an exact-match
guard before the progressive-prefix loop. (Orchestrator to file.)

### P1 (pre-existing) — OPEN: `_RE_BASE_PREFIX` lookbehind admits digit/underscore

`parse_location("1base 北京") → city=Beijing` still occurs. The lookbehind
`(?<![A-Za-z])` excludes only letters. Pre-existing, out of scope for this PR.
Follow-up issue should tighten to `(?<![A-Za-z0-9_])`. (Orchestrator to file.)

---

## Adversarial checks

All four scenarios verified by running commands in this session.

**Scenario 1 — all bracket/paren content is non-city, no remainder city:**

```
parse_location("【高级】（资深）") → country='CN' city=None  ✓
```

`any_shape_matched` becomes True for the bracket probe; the function falls to
the final `any_shape_matched` guard and correctly returns `country='CN'`
without a city. The `re.sub` loop leaves only whitespace for bare-scan, which
finds nothing.

**Scenario 2 — bracket spans entire string:**

```
parse_location("【高级工程师招聘】") → country='CN' city=None  ✓
```

The bracket probe matches, captured token `高级工程师招聘` is not in
`_CITY_PINYIN`, probe falls through. `re.sub` replaces the entire bracket with
`' '`, bare-scan receives `' '`, `_scan_bare_city('')` handles the empty or
whitespace-only case correctly (iterates `_CITY_PINYIN`, `.find()` returns -1
for all cities, returns `None`). Safe.

**Scenario 3 — pseudo-nested brackets `【【北京】】`:**

Step-by-step trace:
- `_RE_BRACKET` uses `[^】]+?` (non-greedy, forbids `】` inside) → matches
  `【【北京】` (captures `【北京`), leaves stray `】`.
- Probe: captured = `【北京`, not in `_CITY_PINYIN` (leading `【` is not CJK),
  falls through; `any_shape_matched = True`.
- `re.sub(_RE_BRACKET, ' ', '【【北京】】')` → `' 】'` (bracket match removed,
  stray `】` remains).
- bare-scan on `' 】'` → `None`. Returns `country='CN' city=None`. ✓

No false city resolution; the stray `】` is harmless.

**Scenario 4 — re.sub leaves adjacent/doubled whitespace around a real city:**

```
parse_location("【高级】  杭州  【资深】") → city='Hangzhou'  ✓
```

`_scan_bare_city` uses `s.find(native)` on the raw string, which handles
any whitespace quantity correctly. Adjacent spaces from `re.sub` do not
disturb bare-scan.

---

## Test summary

```
uv run pytest -q
159 passed, 1 deselected, 4 warnings in 16.87s
```

Fully green. No regressions.

## Lint summary

```
uv run ruff check .
All checks passed!
```

---

## Pre-existing P1s — confirmed still present, still out of scope

Both P1s were verified live during this review (see commands above). Neither
was touched by commits `77da306`, `8e48d67`, or `fde5784`. They remain as
before this PR and are confirmed out of scope per the spec. The orchestrator
should file follow-up issues:

1. Progressive-prefix trim resolves street-name substrings (e.g. `base 北京路工程师 → Beijing`).
2. `_RE_BASE_PREFIX` lookbehind admits digit/underscore boundaries (e.g. `1base 北京 → Beijing`).

---

## Final sign-off

The P0 regression (multiple bracket/paren spans, only first excised) is fully
resolved by switching from per-probe `str.replace` to global `re.sub` over
each shape pattern. The latent variable-shadowing P1 is gone as a side-effect.
All 159 tests pass, lint is clean, and all adversarial scenarios produce
correct output. The two pre-existing P1s remain open for follow-up issues;
they are not regressions from this PR. Clear to merge.
