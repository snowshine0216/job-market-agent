# 001-pr-review verdict — PASS-WITH-NITS

Independent `/code-review` pass on [PR #13](https://github.com/snowshine0216/job-market-agent/pull/13)
(base `autodev/issue-7-detail-page-fetch-feature`, 10 commits since `main`).

Fallback used: `/code-review` skill executed INLINE in the orchestrator session (subagent dispatch
blocked by missing 1M-context credits). Verdict produced by walking the diff at the same medium-effort
bar a fresh `/code-review` agent would have — 5 angle scan + cross-file + 1-vote verify against tests.

## Phase 0 — Diff in scope

```
src/jma/sources/base.py                         |   5 +
src/jma/sources/testerhome.py                   | 256 ++++++++++++++++++---
src/jma/cli.py                                  |  14 +-
config/sources/testerhome.yaml                  |  13 +
tests/cli/test_crawl.py                         |  10 +
tests/sources/test_detail_config_defaults.py    |  10 +
tests/sources/test_testerhome_detail.py         | 141 +++
tests/sources/test_testerhome_with_detail.py    | 171 +++
tests/fixtures/sources/testerhome/detail_*.html |  24 +
```
(Out-of-scope working-tree files for Issue #8 remain untracked.)

## Phase 1 — Five-angle scan

### Angle A — line-by-line scan
- `_fetch_classified` cache-hit branch re-classifies with `headers={}`. **Safe** — `classify()` only reads headers on `Retry-After` for 429s, which a 200 cache hit can't produce.
- The new `elif ... fetched.status_code != 200:` writes a url_cache entry for plain non-200 but deliberately SKIPS 200+block. Matches the documented anti-poison guard.
- Pre-truncate: `remaining = max_jobs - len(collected)` cannot go negative because `len(collected) >= max_jobs` triggers an early return on the prior page; `remaining == 0` yields `page_jobs[:0]` = [].
- YAML label patterns use double-backslash escapes (`\\s`, `\\n`); once parsed they compile to the intended regex. End-to-end test `test_parse_detail_extracts_company_and_salary_from_basic_fixture` confirms.
- `_enrich_from_detail`: `detail.get("company") or job.company` correctly preserves listing data on empty detail string (`"" or job.company` → `job.company`).

### Angle B — removed-behavior auditor
- The original listing-path code wrote a blob and called `on_fetch(url, 200, blob_ref)` **before** classifying. After the refactor, this happens only when classify is OK. This is an **intentional** behaviour change documented in the plan (Task 5 step header: "behavior-preserving for tested paths"). The new behaviour is locked by `test_crawl_with_detail_block_converts_to_partial_harvest` (asserts only 1 blob on disk after the listing succeeds and the detail blocks).
- No guard or validation has been silently dropped.

### Angle C — cross-file tracer
- `_factory_for` signature changed from `(source_name, data_root)` to `(source_name, data_root, with_detail)`. Only caller is `_run_all` inside `crawl()` (same file). Updated to pass `with_detail=with_detail`. No external callers.
- `_ClassifiedFetch` is module-private (leading underscore). Only used by `TesterHomeSource._fetch_classified` callers (`_enrich_page` + `crawl`).
- `_parse_detail` / `_enrich_from_detail` are module-level functions, imported by tests only. No production caller outside `TesterHomeSource._enrich_page`.

### Angle D — language-pitfall specialist
- Python `or` short-circuit semantics on `detail.get("company") or job.company` — fine because empty string is falsy. `0` would also be falsy, but company/salary_raw are strings.
- No mutable default args. No late-binding closures (the lambda-free `_factory_for._make` closes over `cfg`, `data_root`; each call to `_factory_for` produces a fresh closure).
- `re.compile` is called inside `_extract_first_label_value` once per call — not hot enough to need caching but not a bug. If a YAML pattern is malformed regex, `re.compile` raises at runtime; this is a config-error concern, not a code bug.
- `asyncio.sleep` mocking via `_noop_sleep` in tests is consistent with existing patterns.

### Angle E — wrapper/proxy correctness
- `_fetch_classified` is a thin wrapper around `self._http.fetch(...) + classify(...) + blobs.write(...)`. No re-entrancy via `self._cache_get` — cache-get is awaited once at top, result inspected directly. No infinite-loop risk.
- The `_enrich_page` loop guards `halt` before per-job sleep, so a halted-mid-page state does not over-sleep.

## Phase 2 — Verify

All candidate concerns either REFUTED by existing tests or covered by an intentional, documented design choice.

## Phase 3 — Sweep for gaps

Three documentation / design follow-ups (not blockers; all overlap with the inline review at `items/001-review.md`):

1. **`test_crawl_with_detail_falls_back_on_detail_404` docstring is misleading.** Implementation halts on 404 → PartialHarvest; assertions hold because PartialHarvest reports `status=OK`. Suggested rewrite: "404 on a detail page halts further enrichment and converts the run to PartialHarvest, preserving prior listing-only data."
2. **Plain "topic deleted" 404s halt the entire crawl.** Per the plan and CONTEXT.md PartialHarvest entry this is correct, but in real-world TesterHome data, 404s on deleted threads are routine. Follow-up issue: consider per-job degrade for `404 text/plain` vs. PartialHarvest for `429`/`5xx`/soft-blocks.
3. **Cache-hit re-classification uses empty `headers={}`.** Safe today; document this assumption if the cache layer is ever extended to surface response headers.

## Findings JSON

```json
[]
```

(Three nits noted above are documentation/design follow-ups, not defects that would produce a wrong output or crash; per `/code-review` PASS criteria they don't enter the findings array.)

## Verdict: PASS-WITH-NITS — zero blocker bugs, zero latent bugs, 3 doc/design follow-ups documented.
