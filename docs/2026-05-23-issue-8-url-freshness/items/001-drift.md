# Drift check — Item 001 (URL freshness)

Verdict: PASS
Date: 2026-05-23
Comparison: `git diff autodev/issue-8-url-freshness-feature...HEAD`

## Plan tasks vs diff

| Task | Outcome | Notes |
|------|---------|-------|
| 1 — UrlStatus + Job fields | MATCH | `UrlStatus(StrEnum)` with `LIVE/GONE/UNKNOWN` added after `SourceStatus`; `url_status: UrlStatus = UrlStatus.UNKNOWN` and `url_last_checked_at: datetime | None = None` appended to `Job`. `tests/domain/test_models_url_freshness.py` created with all 3 plan tests. |
| 2 — DB schema + migration | MATCH | Two columns added to `_DDL`. `_JOBS_MIGRATIONS` tuple + `_apply_jobs_migrations` helper added above `open_db`. `open_db` calls it. `tests/storage/test_db_migration.py` created with both migration tests. |
| 3 — Conditional upsert | MATCH | `_INSERT_JOB` switched from `INSERT OR REPLACE` to `INSERT … ON CONFLICT(id) DO UPDATE SET`. All non-freshness columns use `excluded.X`. Both `url_status` and `url_last_checked_at` use the `CASE WHEN excluded.url_status IN ('live','gone') THEN excluded.X ELSE jobs.X END` guard. Three upsert-preservation tests appended to `test_db_migration.py`. |
| 4 — _apply_url_freshness helper | MATCH | `_apply_url_freshness(job, *, status_code, checked_at) -> Job` added as a module-level function in `src/jma/sources/testerhome.py`. All 9 tests from the plan added to `tests/sources/test_url_freshness.py`. |
| 5 — _enrich_page wiring | JUSTIFIED DEVIATION | Plan's pseudocode showed a simple `if/else` on status_code. The real `_enrich_page` (from issue #7) uses a `page` object with `page.status_code` and `page.block.kind`. The deviation is the `404/410` check is placed **before** the `page.block.kind is not SourceStatus.OK` check — exactly as required by the plan ("404/410 check correctly placed BEFORE the classify-block check"). The 200 and transient-other branches also call `_apply_url_freshness` correctly. The deviation from the plan's pseudocode is justified by the existing `_fetch_detail` return structure, and the comment in code explicitly explains the reason (`classify() maps 404 to ERROR, but they are NOT anti-bot blocks`). `test_testerhome_with_detail.py` updated with freshness assertions on both the 200 and 404 paths. |
| 6 — CLI gone_urls segment | MATCH | `_summary_lines` updated: `gone_urls=N` appended only when `any(j.url_last_checked_at is not None for j in r.jobs)`; omitted entirely for listing-only crawls. `UrlStatus` imported in `cli.py`. All 3 plan tests in `tests/cli/test_summary.py` present and passing. |
| 7 — CONTEXT.md glossary | MATCH | `## URL freshness` section appended after `## Source`. Covers `live`/`gone`/`unknown` definitions, durable-signal semantics, `url_last_checked_at` meaning, and listing-only crawl behaviour. References ADR 0003 inline. No `data_quality` or `## Data quality` section introduced. |
| 8 — Final regression + lint | MATCH | `uv run pytest` shows **140 passed, 1 deselected** (the 1 deselected is a `live`-marked test, expected). `uv run ruff check . && uv run ruff format --check .` reports "All checks passed!". |

## Justified deviations

- **Task 5 — `_enrich_page` method signature:** The plan's pseudocode showed `_enrich_page` returning `list[Job]`. The existing method (from issue #7) returns `tuple[list[Job], str | None]` (to propagate a `halt` signal back to the caller). The implementation correctly preserves that signature and wires `_apply_url_freshness` into all four branches of the existing control flow. The spirit — "404/410 check before classify-block check, freshness tagged on every exit path" — is fully satisfied. No comment or commit message explicitly flags this deviation, but it is self-evident from the code structure and does not compromise plan intent.

- **Task 5 — e2e durable-signal test location:** The plan placed the transient-500 end-to-end test (`test_transient_500_does_not_overwrite_prior_live_signal`) in `tests/sources/test_testerhome_with_detail.py`. The implementation placed it in `tests/pipeline/test_crawl_e2e.py` instead. The commit comment in that test explicitly explains: "placed in tests/pipeline/test_crawl_e2e.py (Option B) because the plan's own phrasing says 'verified through the full crawl + storage round trip' — that is pipeline-level behaviour, not a source-unit concern. The existing source tests in test_testerhome_with_detail.py do not touch storage." The rationale is sound and the test provides stronger coverage than the plan's intended location would have.

## Out-of-scope changes detected

None. The diff touches only the 11 files expected by the plan:

- `src/jma/domain/models.py`
- `src/jma/storage/db.py`
- `src/jma/sources/testerhome.py`
- `src/jma/cli.py`
- `CONTEXT.md`
- `tests/domain/test_models_url_freshness.py` (new)
- `tests/storage/test_db_migration.py` (new)
- `tests/sources/test_url_freshness.py` (new)
- `tests/sources/test_testerhome_with_detail.py` (modified)
- `tests/pipeline/test_crawl_e2e.py` (modified — e2e durable-signal test, justified deviation above)
- `tests/cli/test_summary.py` (new)

No changes to `domain/dedup.py`, `domain/normalize.py`, `domain/blockage.py`, or any source other than `testerhome.py`. No `## Data quality` section in `CONTEXT.md`.

## Verdict rationale

All eight plan tasks are satisfied. The two deviations are both justified: the `_enrich_page` wiring correctly adapts the plan's pseudocode to the existing `(list[Job], str | None)` return type from issue #7, and the transient-500 e2e test is placed in a more appropriate location (the pipeline test suite) with an explicit explanation in the test docstring.

The durable-signal invariant — the central goal of the feature — is locked by two independent mechanisms as the plan's self-review notes required: (a) the `_apply_url_freshness` helper (return-job-unchanged on transient), tested by 8 unit tests; and (b) the SQL upsert `CASE` clause, tested by 3 storage round-trip tests. The full suite of 140 tests passes with no regressions, and the codebase is lint-clean.
