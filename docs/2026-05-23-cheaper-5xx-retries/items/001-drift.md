# Drift verdict: 001

Verdict: PASS

## Plan tasks vs diff
- Task 1: PASS — `max_retries_5xx: int = 1` added to `RateConfig` in `base.py`; `test_rate_config_default_max_retries_5xx` added to `test_http.py`; committed as `7facd92`.
- Task 2: PASS — `test_fetch_5xx_exhausts_retries` rewritten to assert `attempts==2`, `sleeps==[2]`; committed together with Task 3 in `e3846b9` (plan allowed joint commit).
- Task 3: PASS — `fetch` method split into 429/5xx/other branches using `budget`; docstring updated to explain asymmetry; committed in `e3846b9`.
- Task 4: PASS — `test_fetch_429_uses_max_retries_not_max_retries_5xx` appended, asserts `attempts==4`, `sleeps==[2,4,8]`; committed as `1c6b81f`.
- Task 5: PASS — `test_fetch_5xx_respects_explicit_max_retries_5xx` appended, asserts `attempts==3` with `max_retries_5xx=2`; committed as `34d9167`.
- Task 6: No commit needed (verification-only step). Four ordered commits show clean progression; no fixup commits or ruff style commits indicate suite + lint passed.

## Scope check
No out-of-scope edits. `git diff --name-only` returns exactly three files: `src/jma/sources/base.py`, `src/jma/sources/http.py`, `tests/sources/test_http.py`. Domain layer (`src/jma/domain/`) is untouched.

## AC satisfaction
- AC1: PASS — `test_fetch_5xx_exhausts_retries` asserts `result.attempts == 2` (initial + 1 retry) for a URL returning 503 with default `max_retries_5xx=1`.
- AC2: PASS — `test_fetch_429_uses_max_retries_not_max_retries_5xx` asserts `result.attempts == 4` (initial + 3 retries) for 429, unchanged from before.
- AC3: PASS — `max_retries_5xx: int = 1` added to `RateConfig` in `base.py` with default `1`; no YAML files modified.
- AC4: PASS — all four async tests assert exact `result.attempts` counts (2, 4, 3 for the three new/rewritten cases).
- AC7: PASS — `src/jma/domain/` diff is empty; all changes confined to `src/jma/sources/` and `tests/sources/`.

## Notes
- Minor ordering deviation: the plan placed the `test_rate_config_default_max_retries_5xx` test (Task 1) first in the file, but in the actual diff it appears after the `test_fetch_429_uses_max_retries_not_max_retries_5xx` test (Task 4). The test is functionally identical to what the plan specified; position in the file does not affect correctness.
- Task 2 (test rewrite) and Task 3 (implementation) were committed together in a single commit (`e3846b9`) rather than in two separate commits as suggested by the plan. This is acceptable — the plan explicitly noted that the red-phase test would be committed together with the implementation in "Step 4: Commit Task 2 + Task 3 together".
- The existing `test_fetch_5xx_exhausts_retries` previously asserted `attempts==4` and `sleeps==[2,4,8]`; the rewritten version correctly asserts `attempts==2` and `sleeps==[2]`, consistent with the new `max_retries_5xx=1` default.
