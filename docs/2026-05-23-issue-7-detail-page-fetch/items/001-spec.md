# 001-spec (inferred from plan)

Goal: Add an opt-in detail-page fetch phase to `TesterHomeSource` so each job's `company` and `salary_raw` are populated from its detail page, gated by `cfg.detail.enabled` + a CLI `--with-detail` flag. The default crawl path (listing-only) must remain behaviorally unchanged.

Acceptance criteria:
  - `DetailConfig` extended with `enabled: bool = False`, `company_selectors`, `company_label_patterns`, `salary_selectors`, `salary_label_patterns` (all default to empty tuples); existing YAML loads without error.
  - `config/sources/testerhome.yaml` populated with TesterHome-appropriate selectors and label patterns; `detail.enabled: false` by default.
  - Three detail-page HTML fixtures created: `detail_basic.html` (labels in separate `<p>` tags with whitespace), `detail_minified.html` (no inter-tag whitespace), `detail_blocked.html` (200 body containing soft-block marker).
  - `_parse_detail(body, cfg)` extracts `company` + `salary_raw` from the basic fixture; identical extraction from the minified fixture (locks down child-element iteration robustness); returns empty strings on no-match and when `cfg.detail.enabled` is false.
  - `_extract_first_label_value` iterates block-level child elements (`p, li, dt, dd, blockquote, h1-h6`) so label-scan regex cannot span paragraphs even on minified HTML.
  - `_enrich_from_detail(job, detail, source_name)` returns a new `Job` with company + salary filled and `canonical_id` recomputed (per ADR-0003 latest-wins); `id` is NEVER recomputed; empty detail values do NOT clobber listing data; detail salary wins ONLY when it parses cleanly (don't-downgrade rule).
  - `_fetch_classified(url)` refactor extracted from the listing fetch path; cache-or-fetch → classify → blob/cache write IFF classify is OK; existing `tests/sources/test_testerhome.py` still all green.
  - `_enrich_page(page_jobs)` runs the detail enrichment loop: pre-truncates to `max_jobs - len(collected)` before fetch; sleeps `delay_ms` BEFORE each detail fetch; catches only `httpx.HTTPError` per-job (network errors degrade that job to listing-only); a classify-non-OK on any detail page halts further enrichment and converts the run to PartialHarvest.
  - Detail-block (200 + content_block_marker) does NOT write a blob and does NOT write a successful `url_cache` row for the blocked URL.
  - CLI `--with-detail / --no-detail` flag added to `jma crawl`; overrides `cfg.detail.enabled` via `model_copy` before the source is constructed; appears in `jma crawl --help`.
  - Four integration scenarios under respx-mocked listing + detail all green: detail-enabled success → company+salary populated; detail-disabled → no detail HTTP calls; detail-404 → fallback to listing-only with crawl status=OK; detail-block → PartialHarvest with `reason` starting `"partial:"` and `"detail block"` in it, only one blob written (the listing).
  - Full test suite green (`uv run pytest`); ruff lint + format clean (`uv run ruff check . && uv run ruff format --check .`).

Constraints: Backward-compatible (defaults preserve existing behavior); no schema migration; respects domain ADRs (0001 data_quality deferred; 0003 canonical_id latest-wins); follows CONTEXT.md PartialHarvest semantics for detail-page blocks; Python 3.12 only; tooling via `uv run` (not pip/venv); main branch is protected — landing happens via PR into the feature branch.
