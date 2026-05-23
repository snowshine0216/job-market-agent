# Inline code review verdict: 001

Verdict: PASS-WITH-NITS

## Surface
working-tree diff vs autodev/cheaper-5xx-retries-feature (substituting for bypassed /ship steps 8+9)

Files reviewed:
- `src/jma/sources/base.py` — `max_retries_5xx: int = 1` added to `RateConfig`
- `src/jma/sources/http.py` — retry-budget split by status class; module docstring updated
- `tests/sources/test_http.py` — 3 new tests + 1 rewritten test

## Findings

### Blockers
- none

### Latent bugs
- none

### Nits (non-blocking)

1. **Over-provisioned mock lists in two 5xx tests** (`tests/sources/test_http.py` lines 73 and 118).

   `test_fetch_5xx_exhausts_retries` passes `[httpx.Response(503, text="")] * 4` but with `max_retries_5xx=1` only 2 requests are ever made; 2 entries sit unconsumed.  `test_fetch_5xx_respects_explicit_max_retries_5xx` similarly provides 4 responses but consumes only 3.  The extra entries are harmless (respx does not raise on unused side effects), but the list length no longer carries documentary meaning and a reader might wonder why it is 4.  Consider trimming each list to exactly the expected attempt count (`* 2` and `* 3` respectively), or adding a brief comment explaining the intentional slack.

   `test_fetch_429_uses_max_retries_not_max_retries_5xx` correctly uses `* 4` matching the 4-attempt assertion — that one is fine.

2. **`test_rate_config_default_max_retries_5xx` is a sync test placed after the async regression-pin tests** (`test_http.py` line 106).

   The test is correct and will pass wherever it sits.  Placing it before the async integration tests (closer to where `RateConfig` is first imported, mirroring the "model first, then behavior" pattern visible in the rest of the file) would improve readability.  Not a functional issue.

## Summary

The implementation is correct. The retry-budget split logic in `AsyncHttpClient.fetch` handles all boundary cases without off-by-one errors: `budget == 0` returns on the first attempt, `budget == 1` (5xx default) produces exactly 2 attempts and 1 sleep, `budget == 3` (429 default) produces exactly 4 attempts and 3 sleeps — all consistent with the test assertions. The new `max_retries_5xx` field on `RateConfig` is frozen-pydantic with a default of 1, fully backward-compatible with the existing YAML file and all `RateConfig()` callsites. The domain layer (`src/jma/domain/`) is untouched. The module docstring clearly explains the asymmetry rationale. The two nits are cosmetic (mock list lengths and test ordering) and do not affect correctness or test coverage.
