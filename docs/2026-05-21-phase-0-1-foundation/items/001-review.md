Verdict: PASS-WITH-NITS

## Round 2 — re-review after fix-round 1

All four latents and two of three round-1 nits are correctly fixed. The third nit (Phase-2 TODO comment in `cli.py`) is also present. 93 tests pass, ruff is clean. One new minor nit was found during the fix-round regression scan; no new blockers or latents.

---

## Verification of round-1 findings

### L1 — URL cache write-only: **fixed**

`src/jma/pipeline/crawl.py:54-58` — `_cache_get` now calls `await urlcache.get(db, url=url)` on the happy path; returns `None` immediately when `use_cache=False` (correct `--no-cache` semantics per spec §8). `src/jma/sources/testerhome.py:82-87` — cache-hit branch reads `blobs.read()` from `hit.blob_ref` and sets `status_code=200, headers={}` before the shared `classify()` call; the `else` branch (real fetch) remains the only place that calls `on_fetch` (so cache rows are never double-written). Two required tests exist and assert round-trip behaviour:

- `test_second_run_hits_cache_for_fresh_urls` (line 85): `route1.call_count` and `route2.call_count` are pinned after run 1 and asserted not to increase on run 2. PASS.
- `test_no_cache_skips_reads_but_writes` (line 135): asserts `url_cache` rows are present after two `use_cache=False` runs. PASS. (See nit N1 below for a weakness in this test.)

Cache-hit path calls `classify(status_code=200, headers={}, body_text=..., cfg=...)`. `classify` only consults `headers` when `status_code == 429` (for `Retry-After`); a cached body with `status_code=200` and empty headers is correctly handled — any soft-block markers present in the body still trip the `marker in body_text` check. The `headers={}` shim is safe.

### L2 — Run row dangling on exception: **fixed**

`src/jma/pipeline/crawl.py:75-83` — `try/except Exception` wraps the crawl + insert + finish block; the `except` branch builds a `SourceResult` with `status=SourceStatus.ERROR` and `reason=f"unhandled exception: {type(e).__name__}: {e}"` (captures exception type and message), then calls `finish_run` before re-raising.

`test_unhandled_source_exception_still_finishes_run` (line 183): asserts `pytest.raises(RuntimeError, match="boom")` propagates AND `runs.finished_at is not None` AND `source_results_json` contains `status == "error"`. Both conditions verified. PASS.

### L3 — Hardcoded source="testerhome": **fixed**

`src/jma/pipeline/crawl.py:43,49` — a probe instance is created with no-op callbacks to discover `_probe.name`; the real `_on_fetch` closure tags cache rows with `_probe.name` instead of the literal `"testerhome"`.

`test_cache_rows_tagged_with_source_name` (line 234): uses `_FakeNamedSource(name="fake-source")` and asserts `SELECT DISTINCT source FROM url_cache` equals `["fake-source"]`. PASS.

### L4 — Blobs written for non-200: **fixed**

`src/jma/sources/testerhome.py:93-99` — `blobs.write()` is now gated on `status_code == 200`; non-200 paths set `blob_ref = None`.

`test_blob_not_written_on_blocked_response` (line 157): mocks a 429 response, asserts `list(blobs_dir.rglob("*.gz")) == []`. PASS.

### Nit: `parse_salary` line count: **fixed**

`_try_annual_cny` (11 lines, returns `Salary | None`) and `_try_monthly_k` (10 lines, returns `Salary | None`) extracted at `normalize.py:35-56`. `parse_salary` body is now 40 lines. All 12 parametrized corpus rows in `test_normalize_salary.py` still pass. USD `$120K-$160K` is handled by the pre-check `_RE_USD_ANNUAL` block at line 66-73 (before either helper is called), so the helper fall-through is correct.

### Nit: Dead `or '应届' in s`: **fixed**

Removed. `normalize.py` now only contains `'应届'` inside `_FRESH_TOKENS`; the `any(tok in lower for tok in _FRESH_TOKENS)` expression covers it.

### Nit: Phase-2 TODO comment in `cli.py`: **fixed**

`cli.py:108` — `# Phase 2 TODO: when multi-source is enabled, create one shared run_id before the source loop (spec §2 row 6).` is present.

### QA-side nit (pinned hex values in `test_dedup.py`): **fixed**

`test_canonical_id_pinned_value` asserts `== "445e9bf368e83676a23c3e15a0bfc17c886fa244"` (40 chars). `test_job_id_with_internal_id_pinned_value` asserts `== "29fbf773510b7b61753b8fd080385e27cdf11576"` (40 chars). Both are literal hex strings. PASS.

---

## New findings

### N1 — `test_no_cache_skips_reads_but_writes` weak assertion (nit)

`tests/pipeline/test_crawl_e2e.py:133-167` — the test adds initial mock routes at lines 137-140, then adds duplicate routes inside the loop (lines 146-149). The final assertion `count >= 1` only proves cache rows exist; it does NOT assert the network was hit on _both_ runs (i.e., that `route.call_count == 2` for each page). A future regression where `--no-cache` silently re-enables cache reads would still pass this test as long as at least one cache write occurred. This is a test-coverage nit, not a bug in the production code (which correctly returns `None` on `not use_cache`).

### N2 — Probe factory called twice per `run()` invocation (nit)

`crawl.py:43` — `source_factory` is called once with no-op callbacks to get `_probe.name`, then again at line 60 with real callbacks. For `TesterHomeSource` this is benign (constructor is pure). In future sources with constructor side effects (e.g., opening a connection) this pattern would cause a resource leak. Consider attaching `name` to the `SourceFactory` type or adding a `source_name()` factory companion, but this is Phase-2 work.

### N3 — Double-finish race if `finish_run` itself fails in happy path (nit)

`crawl.py:73` — if `finish_run` in the `try` block raises (e.g., a DB write error), the `except` handler at line 75 catches it and calls `finish_run` again with an error result, overwriting any partial state from the first call. The `UPDATE runs SET ...` in `db.py` is idempotent enough that this is unlikely to cause corruption, but the original `SourceResult` (with real jobs/pages data) would be replaced by the generic error result, losing useful information. Low probability; flagged as nit.

---

## Compliance re-check

| Rule | Status |
|---|---|
| Pure domain functions — no I/O in `domain/*` | PASS — no change to domain layer |
| Frozen pydantic models | PASS — all 8 models retain `ConfigDict(frozen=True)` |
| File line counts | PASS-WITH-NOTE — `testerhome.py` is 282 lines (above the 200-line ideal); no files exceed a hard limit. The bulk is in `_parse_listing`, `_item_to_job`, `_filter_region`, `_filter_keywords` pure helpers that are correctly separated. Acceptable given current scope. |
| No shared mutable state | PASS |
| Small functions | PASS — `parse_salary` now 40 lines; helpers ≤ 11 lines |
| ruff clean | PASS |
