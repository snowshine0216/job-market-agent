Verdict: FAIL

## Summary

The PR delivers a well-structured Phase 0+1 foundation — 84 tests pass, ruff is clean, the domain layer is genuinely pure, models are frozen, and the TDD discipline is evident throughout. However there is one latent defect severe enough to warrant a FAIL: the 24h URL cache is entirely write-only. `cache.get()` is never called anywhere in `src/`, so `TesterHomeSource` re-fetches every URL on every run, the `--no-cache` flag is semantically inverted (it suppresses writes, not reads), and the cache tests only verify insertion — no test verifies that a subsequent fetch is skipped. This is a spec §7.3 step 2 violation that will silently hammer the live site on re-runs. A secondary latent defect (uncaught exceptions leave `runs.finished_at` permanently NULL) is also worth fixing before merge. Two further latent issues (hardcoded source name in cache writes; blobs written for non-200 bodies) and three nits round out the findings.

---

## Findings Table

| file:line | severity | what's wrong | suggested fix |
|---|---|---|---|
| `src/jma/sources/testerhome.py:74` + `src/jma/pipeline/crawl.py:36-43` | **latent** | Cache is write-only; `cache.get()` never called; source always re-fetches; `--no-cache` flag suppresses writes instead of reads (backwards from spec §7.3 step 2 and §8) | Add `conn` parameter to `TesterHomeSource` (or pass a `get_cache` callback); call `cache.get(url)` before `http.fetch()`; only call `on_fetch` to write when a real fetch happens; flip `--no-cache` meaning to bypass reads |
| `src/jma/pipeline/crawl.py:46-58` | **latent** | If `source.crawl()` raises an unhandled exception, `finish_run()` is skipped; `runs.finished_at` stays NULL forever | Wrap body of `async with conn as db:` in try/finally; call `finish_run` with an error sentinel in the finally clause |
| `src/jma/pipeline/crawl.py:40` | **latent** | `source="testerhome"` is hardcoded in the `on_fetch` closure; when Phase 2 adds more sources, all cache rows will be tagged as `testerhome` | Replace with `result.source` after the crawl call, or thread the source name into the closure from `source_factory` context |
| `src/jma/sources/testerhome.py:77-82` | **latent** | `blobs.write()` is called before `classify()` check; empty or error bodies (429, 403) are gzipped to disk and never referenced | Gate the `blobs.write()` call on `fetched.status_code == 200`, or move it after the blockage check |
| `src/jma/domain/normalize.py:51` | nit | `parse_salary` is 51 lines (CLAUDE.md hard limit is < 50) | Extract two `_parse_annual_cny` / `_parse_monthly_k` helpers (3-4 lines each) |
| `src/jma/domain/normalize.py:98` | nit | `'应届' in s` is dead code; `_FRESH_TOKENS` already contains `'应届'` and `any(tok in lower ...)` covers it | Remove `or '应届' in s` |
| `src/jma/cli.py:97-109` | nit | Multi-source loop calls `pipeline_run` once per source, creating one DB `Run` per source; spec §2 row 6 says one Run per CLI invocation | Note is Phase 1 only; add a TODO comment that Phase 2 should create a shared run_id before the source loop |

---

## Detailed Notes

### L1: Cache is write-only — spec §7.3 step 2

`cache.get()` is never invoked anywhere in `src/`. A `grep -rn "cache.get"` across `src/` returns nothing.

`TesterHomeSource.crawl()` calls `self._http.fetch(url)` unconditionally every page, every run. The `on_fetch` callback (wired in `crawl.py`) only calls `urlcache.put()`. The `--no-cache` flag selects between `on_fetch` (real write) and `_noop` (no write), so with `--no-cache=True` nothing is written either — the exact opposite of the spec description ("still writes cache rows; just skips reads").

Consequence: every `jma crawl` re-fetches every page from the live site, even if it was fetched an hour ago. The 24h TTL is inert.

The comment in `testerhome.py` line 76 acknowledges the gap: _"cache integration lives at the pipeline layer in slice 1.11"_ — but `crawl.py` (slice 1.11) only writes, never reads.

**Fix direction:** Pass `conn` (or a `get_cache: Callable[[str], Awaitable[CacheHit | None]]` callback) into `TesterHomeSource`. In the per-page loop, call `get_cache(url)` first; on a fresh hit, read the blob from disk and skip `http.fetch()`. Only write the new blob+cache row when a real fetch happens. The `use_cache` flag should gate the `get_cache` call (skip read on `--no-cache`), not the write.

### L2: Exception leaves Run row dangling

In `crawl.py`, `start_run()` writes a row to `runs` before the crawl starts. If `source.crawl()` raises (e.g. an unhandled `httpx` exception), the code reaches Python's default exception propagation and `finish_run()` is never called. The `runs` row stays with `finished_at = NULL` and `source_results_json = NULL`. Future queries that filter on `finished_at IS NOT NULL` will silently miss incomplete runs.

**Fix direction:**
```python
try:
    result = await source.crawl(...)
    ...
    await insert_jobs(db, run_id, list(result.jobs))
    await finish_run(db, run_id=run_id, source_results=[result])
except Exception:
    await finish_run(db, run_id=run_id, source_results=[
        SourceResult(source="?", status=SourceStatus.ERROR, reason="unhandled exception")
    ])
    raise
```

### L3: Hardcoded `source="testerhome"` in `on_fetch`

`crawl.py` line 40: `source="testerhome"` is a string literal in the `on_fetch` closure. The cache `source` column becomes meaningless when Phase 2 adds Randstad or Bing sources; every cache row for any source will be tagged as `testerhome`. This makes the `source` column in `url_cache` worthless for filtering and debugging.

### L4: Blobs written for non-200 responses

`testerhome.py` lines 77-80 call `blobs.write()` before `classify()`. A 429 response with an empty body generates a gzipped file on disk (`data/raw/testerhome/<date>/<sha1>.html.gz`) that is never referenced by the cache (since `crawl.py` stores `blob_ref=None` for non-200). These files accumulate silently. More importantly, storing failed-fetch blobs intermingles them with valid HTML blobs under the same directory.

---

## Spec Compliance Check

### Decision table (high-risk rows)

| Row | Spec | Compliance |
|---|---|---|
| 4 (dedup) | `job_id = sha1(source:internal_id)` or fallback `sha1(source:norm(title)\|company\|city)`; `canonical_id = sha1(norm(title)\|company\|city)` | PASS — `dedup.py` is correct; `canonical_id` is source-independent; NFKC+lower+collapse consistent |
| 7 (region filter) | NFKC + case-insensitive substring; empty city kept | PASS — `_filter_region` uses `normalize_for_match` for both needle and city; `city is None` is kept |
| 8 (blockage scope) | HTTP + soft-block only; parse-result decisions in per-source loop | PASS — `domain/blockage.py` is pure; end-of-listing in `testerhome.py` crawl loop |
| 9 (PartialHarvest) | Status=OK, jobs=collected, reason starts with `"partial:"` | PASS — implementation matches exactly |
| 11 (disclosure three-way) | `parseable` / `unparseable` / `absent` via `Salary.disclosure` property | PASS — property implemented correctly |

### §3 Module layout — PASS

All required files present; layout matches spec exactly.

### §4 Data models — PASS

All fields present with correct types and defaults. `model_config = ConfigDict(frozen=True)` on every model. `Salary.disclosure` property correct. `StrEnum` used instead of `str`-valued `Enum` from spec — this is fine; `StrEnum` is a clean Python 3.11+ equivalent.

### §5 SQLite schema — PASS

DDL in `db.py` matches spec exactly: all columns, all indexes, FK on `run_jobs`, `PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`. `INSERT OR REPLACE INTO jobs`, `INSERT OR IGNORE INTO run_jobs` semantics correct.

### §6 Blockage classifier decision tree — PASS

First-match-wins order: 429 → 401/403 → >=500 → !=200 → marker → empty body → OK. Matches spec table rows 1–7 exactly. `snippet_around` radius=120 with hard cap at 200 chars.

### §7.3 TesterHome algorithm — PARTIAL FAIL

Steps 1, 3–12 correctly implemented. **Step 2 (cache read) is not implemented.** The source always fetches; `storage.cache.get()` is never called.

### §8 CLI surface — PARTIAL FAIL

Options and defaults match spec. Exit codes are correct (0/2/1). Stdout format matches spec. **`--no-cache` semantics are inverted**: spec says skip cache for fetches but still write; impl skips writes (reads were never done). Since cache reads don't exist, the observable behavior of `--no-cache` is: with flag = writes skipped; without flag = writes happen; in both cases fetches always happen. This is backwards from spec intent.

---

## CLAUDE.md / FP Compliance Check

| Rule | Status |
|---|---|
| Pure functions in `domain/*` — no I/O, no globals, no clock-reading | PASS — all domain files clean; no I/O imports, no `datetime.now` calls |
| Frozen pydantic models | PASS |
| Builders use `model_copy(update={...})` | PASS — only one `model_copy` call in `crawl.py`; correct |
| I/O isolated to `sources/http.py`, `storage/*`, `pipeline/crawl.py`, `cli.py` | PASS — `testerhome.py` is in `sources/` and does legitimate I/O |
| Small functions (<20 lines ideal, <50 hard) | NEAR-FAIL — `parse_salary` is 51 lines (37 functional); over hard limit by one line |
| No deeply nested conditionals (>3 levels) | PASS |
| No shared mutable state | PASS |
| No global mutable state | PASS — `_CITY_PINYIN` is a constant dict |

---

## Test Quality Notes

**Strengths:**
- Tests assert behavior, not implementation (no mock leakage into assertions)
- `respx` used consistently for all network tests
- Clock injection via `now=` param used in `cache.py` and `blobs.py` tests (plan judgment call #10)
- `test_group_by_canonical_id_two_sources` is exactly the right test for the dedup ADR
- `@pytest.mark.live` correctly opt-in

**Gaps/issues:**

1. **No test for cache reads (biggest gap):** `test_cache.py` tests `put`/`get` in isolation, but there is no integration test that verifies a second crawl against the same URLs uses cached data instead of re-fetching. The `test_crawl_e2e.py` test verifies the cache is *populated* but not that it's *consulted*.

2. **`test_crawl_e2e.py` doesn't test `--no-cache` behavior.** A test with `use_cache=False` should assert that no cache rows are written (or reads skipped).

3. **Exception path not tested in `crawl.py`:** No test verifies that the `runs` row gets a proper `finished_at` value when a source raises. This would catch the L2 latent bug.

4. **`_item_to_job` clock call not injected:** `fetched_at=datetime.now(UTC)` in `testerhome.py:233` makes `fetched_at` non-deterministic; plan judgment call #10 says clocks should be injected. This doesn't break any test now but makes future snapshot-style tests fragile.

5. **`test_crawl_e2e.py` line 53:** asserts `source_results[0].jobs >= 1` but fixture `listing_ok.html` has 3 items; the test would still pass even if filtering dropped 2 of them. Could be more precise.
