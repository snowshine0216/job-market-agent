Verdict: PASS

---

## Checklist scorecard

| # | Item | Status | Note |
|---|---|---|---|
| 1 | All eight new tests in `test_normalize_location.py` pass | ✅ | All 8 confirmed PASSED in verbose run |
| 2 | All previously-existing tests still pass | ✅ | 17 pre-existing tests all PASSED |
| 3 | `uv run pytest` fully green | ✅ | 148 passed, 1 deselected (live), 0 failures |
| 4 | `uv run ruff check .` is clean | ✅ | "All checks passed!" |
| 5 | `uv run ruff format .` produces no diff | ✅ | "48 files already formatted" |
| 6 | `_CITY_PINYIN` is unchanged | ✅ | Diff shows no edits to the dict body (only references in new function docstrings/comments) |
| 7 | `_scan_bare_city` body logic unchanged | ✅ | Diff shows only docstring additions; `best_native`/`best_pos`/`s.find` loop is identical |
| 8 | `_REMOTE_TOKENS_CN` / `_REMOTE_TOKENS_EN` constants unchanged | ✅ | No lines added/removed for those constants |
| 9 | `work_mode` extraction at top of `parse_location()` unchanged | ✅ | The `any(tok in s…)` block is untouched in the diff |
| 10 | `docs/adr/0004-location-probe-first-known-city-wins.md` exists with correct status | ✅ | File created; status reads "Accepted — 2026-05-23. Supersedes ADR 0003…" |
| 11 | `0003-location-probe-precedence.md` status updated to "Superseded by ADR 0004" | ✅ | Status block replaced with full superseded text plus forward link |
| 12 | `CONTEXT.md [[Location]]` entry links ADR 0004 and notes 0004 supersedes 0003 | ✅ | Both ADR 0004 and ADR 0003 appear in updated paragraph |
| 13 | No storage/source/pipeline/CLI files touched | ✅ | `git diff --name-only` shows exactly 5 files, all in file map |
| 14 | No GitHub issues closed | ✅ | No `gh issue close` in any commit; out of scope per plan |
| 15 | Commit log shows at least four discrete commits | ✅ | Exactly 4 commits: test(domain) → feat(domain) → docs(adr) → docs(context) |

---

## Acceptance-criteria walkthrough (AC#1–9)

All ACs exercised by named tests in `tests/domain/test_normalize_location.py`. Results from `uv run pytest tests/domain/test_normalize_location.py -v`:

| AC | Input string | Expected city | Test name | Result |
|---|---|---|---|---|
| AC#1 | `（高级）测试工程师 base 北京` | `Beijing` | `test_paren_role_descriptor_falls_through_to_base_prefix_beijing` | PASSED |
| AC#2 | `（资深）开发 base 上海` | `Shanghai` | `test_paren_senior_falls_through_to_base_prefix_shanghai` | PASSED |
| AC#3 | `（实习）数据分析师 base 杭州` | `Hangzhou` | `test_paren_intern_falls_through_to_base_prefix_hangzhou` | PASSED |
| AC#4 | `（兼职）前端 base 深圳` | `Shenzhen` | `test_paren_parttime_falls_through_to_base_prefix_shenzhen` | PASSED |
| AC#5 | `（兼职/实习）后端 base 广州` | `Guangzhou` | `test_paren_parttime_or_intern_falls_through_to_base_prefix_guangzhou` | PASSED |
| AC#6 | `【高级】QA base 成都` | `Chengdu` | `test_bracket_non_city_falls_through_to_base_prefix_chengdu` | PASSED |
| AC#7 | `base 团队 招聘 北京站` | `Beijing` | `test_base_prefix_non_city_falls_through_to_bare_scan_beijing` | PASSED |
| AC#8 | Existing named tests all pass | (no regression) | All 17 pre-existing tests including all named guards | PASSED |
| AC#9 | `（高级）Backend Engineer Remote` → `city=None`, `work_mode=REMOTE` | `city=None`, `work_mode=REMOTE` | `test_paren_role_descriptor_preserves_work_mode_when_no_city` | PASSED |

No AC was left unexercised by a test.

---

## Reported deviations review

**Deviation:** The impl subagent changed `_try_shape_probe` return type from `Location | None` to `tuple[Location | None, bool]`. The `bool` signals whether the probe's regex actually fired (regardless of whether the captured token was a known city). `parse_location()` tracks `any_shape_matched`; if all probes fall through AND `any_shape_matched=True`, it returns `Location(country="CN", city=None, district=None, work_mode=work_mode)` instead of the bare `Location(work_mode=work_mode)`.

**Code location:** `src/jma/domain/normalize.py` lines 259–291 (`_try_shape_probe`) and 308–331 (`parse_location`).

**Motivating test:** `tests/domain/test_normalize_location.py::test_unknown_native_city_in_brackets_yields_none_district` (line 95–101 on both `main` and this branch). This test asserts `loc.country == "CN"` for input `【厦门】Senior QA` — a pre-existing test (added in commit `cd6789a`, predating this branch).

**Why the plan's simpler code would have broken it:** The plan's code returns `None` from `_resolve_native_city` when a captured token is not in `_CITY_PINYIN`, which propagates as `None` from `_try_shape_probe`. With no `any_shape_matched` tracking, after all probes fall through and bare-scan misses, `parse_location()` would return `Location(work_mode=work_mode)` — which has `country=None`. The pre-existing test asserts `country == "CN"`, so it would have FAILED under the plan's unmodified code block.

**Verification:** Running the plan's code mentally:
- Old behavior (pre-branch): bracket matched `【厦门】`, `_build_location("厦门", ...)` was called immediately → returned `Location(country="CN", city=None, ...)`. Country was always "CN" because `_build_location` always set it.
- Plan's proposed refactor (pure `Location|None` without `any_shape_matched`): bracket regex fires, `_resolve_native_city("厦门")` returns `None` (not in vocab), fall-through, bare-scan misses, final return is `Location(work_mode=UNKNOWN)` with `country=None`. This breaks the pre-existing test.

**Decision: ACCEPTED (PASS-eligible).** The deviation is principled: it preserves the pre-existing behavioral contract (`country="CN"` when a CJK-shaped probe matched, even if vocabulary is absent) that the plan inadvertently omitted from its code block. The adaptation is minimal, localised, and in-spirit with the spec's requirement that existing tests must still pass — specifically the test named in the plan's checklist item #2 (`test_unknown_native_city_in_brackets_yields_none_district`). It does not add scope or change any public contract beyond what the spec intended.

---

## Scope-creep check

Files modified on the branch (`git diff --name-only main..HEAD`):

| File | In plan file map? | Decision |
|---|---|---|
| `tests/domain/test_normalize_location.py` | Yes (Modify) | In-scope |
| `src/jma/domain/normalize.py` | Yes (Modify) | In-scope |
| `docs/adr/0004-location-probe-first-known-city-wins.md` | Yes (Create) | In-scope |
| `docs/adr/0003-location-probe-precedence.md` | Yes (Modify) | In-scope |
| `CONTEXT.md` | Yes (Modify) | In-scope |

No files outside the plan's file map were touched.

---

## Out-of-scope guardrail check

- `_CITY_PINYIN` dict: unchanged. Diff shows only references in docstrings/comments; the dict body (`"北京": "Beijing"` … `"重庆": "Chongqing"`) is unmodified.
- `_scan_bare_city` function body: unchanged. Diff shows a docstring update and one comment line edit; the `for native in _CITY_PINYIN` / `s.find(native)` / `best_pos` loop is identical.
- `work_mode` regex / `_REMOTE_TOKENS_CN` / `_REMOTE_TOKENS_EN`: unchanged. No `+`/`-` lines touching those constant definitions.
- Storage/source/pipeline files: not touched.

All guardrails confirmed clean.

---

## Test count

New test functions added in `tests/domain/test_normalize_location.py`: **8**

1. `test_paren_role_descriptor_falls_through_to_base_prefix_beijing`
2. `test_paren_senior_falls_through_to_base_prefix_shanghai`
3. `test_paren_intern_falls_through_to_base_prefix_hangzhou`
4. `test_paren_parttime_falls_through_to_base_prefix_shenzhen`
5. `test_paren_parttime_or_intern_falls_through_to_base_prefix_guangzhou`
6. `test_bracket_non_city_falls_through_to_base_prefix_chengdu`
7. `test_base_prefix_non_city_falls_through_to_bare_scan_beijing`
8. `test_paren_role_descriptor_preserves_work_mode_when_no_city`

Total test count in file went from 17 to 25.

---

## Final summary

The implementation faithfully executes the plan across all 4 discrete commits. The single reported deviation — tracking `any_shape_matched` via a `tuple[Location|None, bool]` return — is principled: the plan's simpler code block would have silently broken the pre-existing `test_unknown_native_city_in_brackets_yields_none_district` test (which asserts `country=="CN"` on a bracket-match-to-unknown-city path). The adaptation is minimal and in-spirit. All 15 checklist items pass, all 25 location tests pass (148 total), ruff is clean, and no out-of-scope files were touched. The ship phase can proceed.
