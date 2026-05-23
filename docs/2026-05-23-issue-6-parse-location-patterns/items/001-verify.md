# 001 — /verify verdict

Verdict: PASS

## How

No web entry point exists; the `/verify` skill was not applicable. Used a structured acceptance-criteria walkthrough instead: ran each corresponding test individually and collectively via `uv run pytest tests/domain/test_normalize_location.py -v` (17 tests, all PASS), confirmed the full suite (`uv run pytest`, 104 passed 1 deselected), verified ruff lint+format on the touched files, inspected the probe-order chain in `parse_location`, and exercised five adversarial titles interactively via `uv run python -c`.

## Acceptance criteria walk-through

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | `（武汉）` → `city=Wuhan, country=CN, district=None` | PASS | `test_chinese_paren_city` PASSED |
| 2 | `（杭州·余杭）` → `city=Hangzhou, district=余杭, country=CN` | PASS | `test_chinese_paren_city_district` PASSED |
| 3 | `base 北京` → `city=Beijing, country=CN` | PASS | `test_base_prefix_city` PASSED |
| 4 | `深圳招聘…` → `city=Shenzhen, country=CN` | PASS | `test_bare_city_at_start` PASSED |
| 5 | `(Remote)` → `city=None, district=None, country=None, work_mode=REMOTE` | PASS | `test_english_paren_does_not_match` PASSED |
| 6 | `Database` substring must NOT trigger base-prefix probe | PASS | `test_database_does_not_trigger_base_prefix` PASSED |
| 7 | `深圳/广州…` → leftmost city wins (`city=Shenzhen`) | PASS | `test_bare_scan_leftmost_city_wins` PASSED |
| 8 | `【厦门】` → `city=None, district=None, country=CN` (no stuffing) | PASS | `test_unknown_native_city_in_brackets_yields_none_district` PASSED |
| 9 | Probe precedence: bracket → paren → base-prefix → bare-scan, first hit wins | PASS | Code inspection confirms chain; `parse_location("【杭州】base 北京")` → `city=Hangzhou` (bracket wins) |
| 10 | Existing five tests (`test_brackets_city_only`, `test_brackets_city_district`, `test_remote_token_inside_brackets`, `test_remote_english_no_brackets`, `test_no_brackets_no_city`) pass | PASS | All 17 tests in file PASSED (includes renamed equivalents) |
| 11 | `uv run pytest tests/domain` is green | PASS | 17 passed in 0.05s |
| 12 | `uv run pytest` (full suite, live excluded) is green | PASS | `104 passed, 1 deselected` |
| 13 | `uv run ruff check . && ruff format --check` is clean on touched files | PASS | `All checks passed! 2 files already formatted` |

## Adversarial exploration

| Input | Output | Expected | Verdict |
|-------|--------|----------|---------|
| `""` | `Location()` (all None, work_mode=unknown) | `Location()` | PASS |
| `"   "` | `Location()` (all None, equals `Location()`) | `Location()` | PASS |
| `"Senior Engineer @ Beijing"` | `city=None, country=None` | `city=None` (English "Beijing" not in CJK vocab) | PASS |
| `"Remote-friendly \| base 上海"` | `city='Shanghai', country='CN', work_mode=REMOTE` | `city=Shanghai, work_mode=REMOTE` | PASS |
| `"【北京】base 上海 深圳招聘"` | `city='Beijing', country='CN'` | `city=Beijing` (bracket wins) | PASS |

## Summary

All 13 acceptance criteria pass and all 5 adversarial cases behave as expected. The probe-precedence chain (bracket → paren → base-prefix → bare-scan) is correctly implemented as a single `if m is None` cascade in `parse_location`. The `_build_location` helper correctly drops unknown cities rather than stuffing them into `district`. No regressions in the wider suite (104 tests green). The implementation is ready to merge.
