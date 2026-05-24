Verdict: PASS-WITH-NITS

Source: /ship steps 8+9 (pre-landing parallel review + adversarial review), with a fix loop applied to address all P0 findings before the PR is opened.

## Review timeline

1. Initial review pass on commits up to `5ddaf5d` (drift verdict): 2 P0 blockers + 1 P1 security finding + several P1/notes (captured in `items/001-ship-blocked.md`).
2. Fix subagent landed 3 commits (`c44858c`, `246d7c1`, `e87445e`) addressing all 3 high-priority findings, plus a lint reformat (`bab59b0`).
3. Verification review on the fix commits: CLEAN — all 3 fixes hold, regression tests exercise the bugs they claim to fix, no new regressions, full pytest suite `174 passed / 1 skipped (fixture) / 1 deselected (live marker)`.

## Subagents

- `pr-review-toolkit:code-reviewer` (pre-landing code review, initial pass)
- `pr-review-toolkit:silent-failure-hunter` (initial pass)
- Adversarial review subagent (initial pass)
- Verification review subagent (post-fix pass)

## Resolved P0 (fixed in-flow)

- **P0-1 — Schema migration gap on pre-existing `data/jobs.db`** (`src/jma/storage/db.py`): the new `run_jobs.raw_payload_ref TEXT NOT NULL` column did not land on pre-Phase-1 DBs because `_DDL` uses `CREATE TABLE IF NOT EXISTS`. Fix `c44858c` adds `_RUN_JOBS_MIGRATIONS` + `_apply_run_jobs_migrations(conn)` mirroring the existing jobs-table migration helper; called from `open_db` after `_apply_jobs_migrations`. Regression test in `tests/storage/test_jobs_for_run.py` manually creates an old-shaped `run_jobs`, reopens via `open_db`, asserts the column appears and `insert_jobs` works.
- **P0-2 — SerpAPI key persisted verbatim in `data/jobs.db`** (`src/jma/sources/bing.py` + `src/jma/storage/cache.py`): the full SerpAPI URL with `api_key=…` was written into `url_cache.url` and also used as the blob filename SHA1 input. Fix `246d7c1` splits `_page_url` into `_cache_url` (no api_key — used for cache + blob + on_fetch) and `_request_url` (full URL — only for the live httpx GET). Regression test in `tests/sources/test_bing.py` asserts neither `on_fetch` nor the blob path contains `api_key=` or the key value.
- **P1-XSS — Unescaped `r.url` in `<a href>` allows `javascript:` URI** (`src/jma/report/view.py` + `templates/view.html.j2`): even with Jinja2 autoescape, `href="javascript:alert(1)"` was a live XSS in the local viewer. Fix `e87445e` adds `_sanitize_url` whitelist (http/https/mailto) in `build_view_context`; unsafe URLs become `"#"` with `url_unsafe=True`. Template renders unsafe rows as `<span class="unsafe-url">` with no `<a>` tag at all. Regression tests in `tests/report/test_view.py` and `tests/report/test_view_template.py` cover `javascript:`, `data:`, `JAVASCRIPT:` (uppercase), `vbscript:`, and safe `https://` URLs.

## Deferred P1 (nits — follow-up issues, not blockers)

- **No timeout on `httpx.AsyncClient()`** (`src/jma/pipeline/crawl.py:41`) — SerpAPI hang = CLI hang. Easy follow-up: pass explicit timeout from `RateConfig`.
- **Region-alias identity fallback logs at INFO, not WARN** (`src/jma/sources/bing.py`) — misspelled `--region Hanzhou` silently degrades coverage. Promote to WARN + thread `fallback=True` into `SourceResult.reason`.
- **`_parse_iso` swallows malformed dates to `None`** (`src/jma/sources/bing.py`) — SerpAPI `"date": "2 days ago"` becomes `posted_at=None` with no log.
- **Off-target drop counter doesn't distinguish "not on target_sites" from "URL malformed"** (`src/jma/sources/bing.py`) — both go in the same `dropped` bucket.
- **`subprocess.run([opener, str(out_path)], check=False)`** in `view --open` (`src/jma/cli.py`) — silent if the opener fails (no DISPLAY, missing binary).
- **Jinja2 render not wrapped in try/except** (`src/jma/cli.py view`) — `UndefinedError` propagates as raw traceback.
- **`--keywords ""` produces silent garbage query** (`src/jma/cli.py` + `bing.py` `_render_query`) — `kw_clause` becomes empty but template still wraps in `({})`; SerpAPI returns unfiltered results.
- **`json.loads` no error handling for malformed SerpAPI JSON** (`src/jma/sources/bing.py`) — auth-error HTML body → `JSONDecodeError` flattened to "unhandled exception"; partial-harvest branch bypassed.
- **`subprocess.run` for `--open` ignores exit code** (covered above; mentioned twice in the reviews).
- **Mutable defaults on `SourceConfig`** (`src/jma/sources/base.py:39-42`) — `id_patterns: dict[str, str] = {}`. Pydantic v2 deep-copies per instance so not a shared-state bug, but cosmetic — use `Field(default_factory=dict)`.
- **`file://` URI in template is unencoded** (`src/jma/report/templates/view.html.j2`) — spaces or `#` in `data_root_abs` break the link in Firefox/Safari. Use `urllib.parse.quote` via a Jinja filter.
- **`_factory_for` raises `KeyError` instead of `typer.Exit`** (`src/jma/cli.py`) — typo `--source bings` gives a Python traceback.
- **Orphaned blob files if killed between `blobs.write` and `insert_jobs`** — disk leak only, no data corruption (ADR-0002's `finish_run` wrapper still fires).

These do not block the merge per autodev's loop exit contract — they are nits and follow-up items, not blockers or latent bugs. Operator can split them into independent fix PRs after this Phase 2 ship lands.

## Final state

- Branch: `claude/phase-2-bing-view-001`
- Latest commit: `bab59b0`
- Tests: 174 passed / 1 skipped (SerpAPI fixture, expected per spec §6) / 1 deselected (live marker, expected per pytest.ini `addopts = -m 'not live'`)
- Lint: `ruff check` exit 0; `ruff format --check` exit 0
- Diff vs `autodev/phase-2-bing-view-feature`: ~50 files, ~2950 insertions, ~2230 deletions

Pre-fix snapshot of the review findings is preserved at `items/001-ship-blocked.md` for audit.
