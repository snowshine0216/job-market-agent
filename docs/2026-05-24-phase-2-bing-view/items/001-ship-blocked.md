# Ship-blocked — review findings from /ship steps 8+9

Source: 3 parallel review subagents on `claude/phase-2-bing-view-001` vs `autodev/phase-2-bing-view-feature`:
- `pr-review-toolkit:code-reviewer`
- `pr-review-toolkit:silent-failure-hunter`
- Adversarial review (general-purpose, sonnet)

## P0 (must fix before push)

### P0-1: Schema migration gap on pre-existing `data/jobs.db`

**File:** `src/jma/storage/db.py` — `_DDL` and `_apply_jobs_migrations`

**Issue:** Phase 2 adds `run_jobs.raw_payload_ref TEXT NOT NULL` to `_DDL`. Because `_DDL` uses `CREATE TABLE IF NOT EXISTS run_jobs (...)`, the new column does NOT land on a pre-Phase-1 database. Operators who skip the spec §2 row 16 manual wipe hit `sqlite3.OperationalError: table run_jobs has no column named raw_payload_ref` on the first `insert_jobs` call, crashing mid-crawl.

`_apply_jobs_migrations` already handles the analogous case for the `jobs` table by issuing `ALTER TABLE` and swallowing the duplicate-column-name `OperationalError`. The same pattern needs to apply to `run_jobs`.

**Spec tension:** §4 declares the change "migration-free" and §2 row 16 makes the wipe a manual step. The reviewer's finding is a defense-in-depth concern, not a spec contradiction. **Resolution:** add the ALTER TABLE migration anyway — defensive, keeps the spec's "no CLI command to wipe" intent, and prevents an OperationalError that the user won't easily map back to "you forgot to wipe."

**Fix:**
1. Add `_RUN_JOBS_MIGRATIONS` tuple with `("raw_payload_ref", "ALTER TABLE run_jobs ADD COLUMN raw_payload_ref TEXT NOT NULL DEFAULT ''")`.
2. Add `_apply_run_jobs_migrations(conn)` mirroring `_apply_jobs_migrations` — swallow `OperationalError` whose message contains the exact phrase `duplicate column name`.
3. Call it from `open_db` after the existing `_apply_jobs_migrations(conn)` call.
4. Add a regression test in `tests/storage/test_jobs_for_run.py` that creates a `run_jobs` table without the column, opens the DB, and asserts the column is present.

### P0-2: SerpAPI key persisted verbatim in `data/jobs.db`

**Files:** `src/jma/sources/bing.py` (URL construction), `src/jma/storage/cache.py` (writes the URL into `url_cache.url`)

**Issue:** `_page_url()` builds `https://serpapi.com/search?engine=bing&q=...&api_key=<SERPAPI_KEY>...` and passes the **full URL with api_key** to the pipeline's `on_fetch` / `cache_get` callbacks. The URL is then written verbatim to `url_cache.url` (and the SHA1 hash of the URL is the blob filename). The key survives `SERPAPI_KEY` rotation, ends up in backups, and is shared if the DB is copied. The blob-on-disk filename hash also changes if the key rotates, fragmenting the cache unnecessarily.

**Fix:** strip `api_key=…` from the URL before passing it to `_on_fetch` / `_cache_get` / `blobs.write`. Keep the api_key in the actual HTTP request (either in the URL sent to httpx OR as an `Authorization` / query param at request time, not in the cache key).

Concrete approach:
1. In `bing.py`, separate `_page_url()` into two: `_cache_url(page)` returns the URL without `api_key`; `_request_url(page)` returns the URL with `api_key` for the actual httpx GET.
2. Pass `_cache_url(page)` to `_on_fetch`, `_cache_get`, and `blobs.write`. Use `_request_url(page)` only for the httpx GET.
3. Add a regression test in `tests/sources/test_bing.py` that asserts `api_key=` does not appear in any stored `url_cache.url` row nor in the URL passed to `blobs.write`.

## P1 included in this fix (one security issue)

### P1-XSS: Unescaped `r.url` in `<a href>` allows `javascript:` URI

**File:** `src/jma/report/templates/view.html.j2`

**Issue:** Jinja2 autoescape escapes the URL for HTML, but `<a href="javascript:alert(1)">` is still a clickable XSS vector in the local viewer. Crafted SerpAPI results (or a poisoned DB) could inject JS that runs when the operator clicks a row.

**Fix:** in `report/view.py`'s `build_view_context`, sanitize each row's `url` to drop anything that isn't `http:`/`https:`/`mailto:`. Replace disallowed URLs with `"#"` and add a `url_unsafe: True` flag so the template can render them as plain text instead of a link. Regression test in `tests/report/test_view.py` covers `javascript:` and `data:` schemes.

## P1 deferred to follow-up (notes only)

The other P1s (no httpx timeout, region-alias log-level, malformed `_parse_iso` swallow, off-target drop counter split, `subprocess.run(check=False)`, Jinja render wrapping, `--keywords ""` silent garbage query, json.loads error handling, orphaned blobs on crash, `--out` permission errors) are noted but deferred. Most are UX papercuts; none expose credentials or break correctness on the canonical happy path.

---

After fix lands, re-run /ship steps 8+9. On clean verdict, the review file becomes `items/001-review.md` (this file is the pre-fix snapshot and stays on disk for audit).
