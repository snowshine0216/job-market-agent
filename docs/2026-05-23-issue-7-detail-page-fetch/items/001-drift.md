# 001-drift verdict — PASS

Compared `git diff main..HEAD` (10 commits, 0d689a0..268dc86) against the user-authored plan at
[docs/superpowers/plans/2026-05-23-issue-7-detail-page-fetch.md](../../superpowers/plans/2026-05-23-issue-7-detail-page-fetch.md).

## Plan tasks → implementation

| Task | Plan summary | Status |
|------|--------------|--------|
| 1 | Extend `DetailConfig` (enabled, company_selectors, company_label_patterns, salary_selectors, salary_label_patterns) + populate `testerhome.yaml` + defaults test | ✅ commit `fe588bc` |
| 2 | Three fixtures: `detail_basic.html`, `detail_minified.html` (no inter-tag whitespace), `detail_blocked.html` (contains `系统繁忙，请稍后再试` marker) | ✅ commit `9f17202` |
| 3 | `_parse_detail(body, cfg)` + `_extract_first_label_value` with per-child-block iteration (`_BLOCK_CHILD_CSS = "p, li, dt, dd, blockquote, h1-h6"`); 4 unit tests incl. minified-fixture regression | ✅ commit `9ae884a` |
| 4 | `_enrich_from_detail(job, detail, source_name)` — recomputes `canonical_id` only (no `id` recomp), don't-downgrade salary rule (parsed listing salary preserved against unparseable detail); 5 unit tests | ✅ commit `c19c5ba` |
| 5 | Extract `_fetch_classified` + frozen `_ClassifiedFetch` dataclass; cache-or-fetch → classify → blob/cache write IFF classify is OK; existing listing tests still green | ✅ commit `a823380` |
| 6 | `_enrich_page` with sleep-before-fetch, `httpx.HTTPError`-only catch, classify-non-OK halt → PartialHarvest; `max_jobs` pre-truncation in `crawl` | ✅ commit `6904b5f` |
| 7 | Four respx-mocked integration scenarios: enabled-success, disabled-skips, 404-fallback, block-converts-to-partial-harvest (verifies no detail blob written when blocked) | ✅ commit `3f48f5f` |
| 8 | `--with-detail/--no-detail` Typer flag on `jma crawl`; `_factory_for` takes `with_detail` and `model_copy`s `cfg.detail.enabled=True`; help-text smoke test | ✅ commit `49b663c` |
| 9 | Full pytest green + ruff lint + format clean | ✅ commit `268dc86` (ruff format applied to Task 8/9 changes) |

## Behaviour invariants verified by tests

- ✅ Existing listing tests (`tests/sources/test_testerhome.py`, 9 tests) all pass — Task 5 refactor is behaviour-preserving on the tested paths.
- ✅ Default `cfg.detail.enabled=False` skips detail HTTP entirely (`test_crawl_with_detail_disabled_skips_detail_fetch`, `detail_route.call_count == 0`).
- ✅ Detail 404 → listing-only fallback (`test_crawl_with_detail_falls_back_on_detail_404`, `result.status == OK`).
- ✅ Detail 200 + block marker → PartialHarvest with `reason.startswith("partial:")` and `"detail block" in result.reason`; only the listing blob is on disk (`detail_blob_count == 1`).
- ✅ canonical_id recomputed when company changes; `id` invariant (`test_enrich_fills_company_and_salary_and_recomputes_canonical_id_only`).
- ✅ Listing parseable salary not degraded by unparseable detail (`test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable`).
- ✅ Minified-HTML regression locked (`test_parse_detail_extracts_correctly_from_minified_fixture`).

## Final tallies

- 10 commits on `claude/issue-7-detail-page-fetch-001` since `main`.
- Full suite: **119 passed, 1 deselected** (live), 4 collection warnings (pre-existing, unrelated to this change).
- `ruff check .` → All checks passed.
- `ruff format --check .` → 44 files already formatted.

## Out-of-scope working-tree files (untouched, per MASTER-PLAN.md)

- `docs/adr/0003-url-freshness-as-durable-signal.md` — belongs to Issue #8.
- `docs/superpowers/plans/2026-05-23-issue-8-url-freshness.md` — belongs to Issue #8.

These remain untracked on this branch.

## Verdict: PASS — no drift from plan; ready for ship.
