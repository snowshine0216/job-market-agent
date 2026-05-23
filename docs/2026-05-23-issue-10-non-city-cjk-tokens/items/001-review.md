# 001 — Review (captured inline from /ship steps 8+9)

Verdict: **PASS-WITH-FIX** (initial verdict was FAIL; in-flow fix landed in commits `d82e390`, `5cdcf4d`, `22c02fb`).

Subagents: `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`, adversarial (general-purpose).

Test count after fix: 154 passed, 1 deselected, 0 failures (was 148 before fix; +6 regression tests).

---

## Original P0 — silent data corruption: bracket non-city now masks wrong bare-scan match

**Reporter:** adversarial review · **Status:** FIXED in `5cdcf4d`

**Repro before fix:**
```
parse_location("【北京路】QA工程师")          → city="Beijing"  ❌ (北京路 is in Shanghai)
parse_location("软件测试工程师【北京东路招聘中心】")  → city="Beijing"  ❌
```

**After fix (verified by post-fix smoke):**
```
parse_location("【北京路】QA工程师")          → city=None  ✅
parse_location("软件测试工程师【北京东路招聘中心】")  → city=None  ✅
```

Fix design: after all shape probes fall through, `_scan_bare_city` now runs on the input with the probe-captured non-city substrings excised. ADR 0004 §Consequences updated to document the excision rule. Regression tests pinned in `tests/domain/test_normalize_location.py`.

## Original P0 (debatable) — REMOTE sentinel hard-codes `work_mode`

**Reporter:** silent-failure-hunter · **Status:** FIXED in `5cdcf4d`

REMOTE sentinel now composes `work_mode` correctly: caller-supplied `REMOTE` / `HYBRID` is preserved; otherwise upgrades to `REMOTE`. Also preserves `country="CN"` (was missing — P1 below).

## Original P1 — REMOTE sentinel drops `country="CN"`

**Status:** FIXED in `5cdcf4d` · regression test `test_remote_sentinel_in_bracket_preserves_country_cn`.

## Original P1 — base-prefix probe bypasses `_resolve_native_city`

**Status:** FIXED in `5cdcf4d` · base-prefix probe now routes through `_resolve_native_city`. Future enrichment lands in one place.

## Original P1 — undocumented `【北京朝阳】` behaviour change

**Status:** RESOLVED by the P0 fix. With excision, `【北京朝阳】` returns `city=None` again (the bracketed `北京朝阳` is excised before bare-scan, so `北京` isn't visible). Regression test pinned. ADR 0004 §Consequences documents the excision-rule trade-off and the middot mitigation (`【北京·朝阳】` works as before).

## Original P1 — misleading test comment

**Status:** FIXED in `d82e390` · comment now accurately describes why `（兼职/实习）` doesn't match the paren regex (`/` breaks the `[一-鿿]{2,4}` shape).

## Notes (non-blocking, unchanged from original review)

- `_build_location` and `_resolve_native_city` overlap on the REMOTE sentinel + city lookup — minor maintenance hazard, but both branches now have consistent contract behaviour.
- No `re.error` guard around `pattern.search()` — patterns are module-level constants so not a real risk.
- Probe loop correctly returns on first hit; no double-fire risk.

## Post-fix verification

- `uv run pytest -q` → `154 passed, 1 deselected, 4 warnings`
- `uv run ruff check .` → `All checks passed!`
- Manual smoke (6 cases) — all expected outputs match (see orchestrator log)

Ready for `/ship` to proceed to step 10 (version bump) → push → PR.
