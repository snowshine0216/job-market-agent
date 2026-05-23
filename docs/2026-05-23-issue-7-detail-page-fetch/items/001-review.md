# 001-review verdict — PASS-WITH-NITS

Inline diff review against the PR diff (10 commits on `claude/issue-7-detail-page-fetch-001`,
target base `autodev/issue-7-detail-page-fetch-feature`). Captures the "/ship steps 8+9"
inline review that the orchestrator owes per the autodev contract; full `/code-review`
will run separately and produce `items/001-pr-review.md`.

## Correctness checks performed

- **Pure vs. effect separation** — `_parse_detail`, `_extract_first_label_value`, `_enrich_from_detail` are pure HTML/data transforms with no I/O. `_fetch_classified`, `_enrich_page` are effect-heavy and live on the source class. ✅
- **Immutability** — `Job` is frozen pydantic; enrichment uses `job.model_copy(update={...})`. `_ClassifiedFetch` is `@dataclass(frozen=True)`. ✅
- **`id` invariant** — `_enrich_from_detail` recomputes only `canonical_id`. `job_id(source, internal_id, ...)` is `sha1("testerhome:internal_id")` per dedup.py; ADR-0003 is honoured. ✅
- **Don't-downgrade salary rule** — `if candidate.parsed or not job.salary.parsed: new_salary = candidate`. Locked by `test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable`. ✅
- **Cache-poison guard** — `_fetch_classified` writes blob + calls `on_fetch` only when `block.kind is OK and status_code == 200`. The 200-with-block-marker case writes nothing. Non-200 (404/5xx) still calls `on_fetch(url, status, None)` so a future run knows we tried. ✅
- **Pre-truncate before detail HTTP** — `page_jobs = page_jobs[:remaining]` runs before `_enrich_page`. `remaining` can be `0` (yields `[]`) but never negative because the prior page's `len(collected) >= max_jobs` branch returns immediately. ✅
- **Detail enrichment failure isolation** — `httpx.HTTPError` swallowed per-job; any other exception (disk write, DB write) propagates out of `_enrich_page` and is handled by the pipeline's outer `finally`/`finish_run`. ✅
- **Detail block → PartialHarvest** — `halt` is set on any non-OK detail classification; outer `crawl` returns `SourceResult(status=OK, reason="partial: stopped at page N (detail block: …)")`. Locked by `test_crawl_with_detail_block_converts_to_partial_harvest`. ✅
- **Help text + factory wire-up** — `--with-detail/--no-detail` reaches `_factory_for(..., with_detail=with_detail)`; flag confirmed in `jma crawl --help`. ✅

## Nits (non-blocking)

1. **Misleading docstring in `test_crawl_with_detail_falls_back_on_detail_404`.** The docstring says "Crawl still succeeds with listing-only data" — but the implementation (per plan Q2) halts on a 404 detail response (404 → `classify` returns `ERROR` → `_enrich_page` sets `halt` → crawl returns `PartialHarvest`). The test assertions (`result.status == OK`, `len(result.jobs) == 1`, `company is None`) still hold because PartialHarvest reports `status=OK`. Suggested clarification: "404 on a detail page halts further enrichment and converts the run to PartialHarvest, preserving prior listing-only data." Not a behaviour bug; just a docstring nit.

2. **404 = halt-the-whole-crawl is aggressive for "topic deleted" 404s.** The plan (Q2) and CONTEXT.md PartialHarvest entry both endorse halting on classify-non-OK, so this is the spec, not a deviation. But in real-world TesterHome data, individual topic 404s (deleted threads) are routine. Worth a follow-up issue to consider per-job degrade for plain `404 Not Found` (text-body) while keeping halt-and-PartialHarvest for `429`/`5xx`/soft-blocks. Out of scope for this PR.

3. **Cached body re-classified with empty `headers={}`.** When `_cache_get` returns a hit, we re-classify using `headers={}`. `classify()` only reads headers for `Retry-After` on 429 responses, which can never come from a 200 cache hit, so this is safe today. If a future check on cached bodies needs response headers, the cache layer (`CacheHit`) would need to start preserving them. Documenting for awareness, not requesting a fix.

## Verdict: PASS-WITH-NITS — no blocker bugs, no latent bugs; 3 documentation/design nits.
