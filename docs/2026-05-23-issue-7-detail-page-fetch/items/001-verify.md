# 001-verify verdict — PASS

Non-web project (Python 3.12 CLI `jma`) → verifier is **/verify** (XOR /qa per autodev contract).
Verify dispatched inline (subagent dispatch blocked by missing 1M-context credits).

## Smoke tests on the merged sub-branch

### Entry-point: `uv run jma --help`
```
 Usage: jma [OPTIONS] COMMAND [ARGS]...
 jma — job-market-agent CLI.
 ...
 Commands:  crawl
```
✅ CLI loads, root help works.

### Entry-point: `uv run jma crawl --help`
```
--with-detail      --no-detail             Fetch each job's detail page
                                           to populate company/salary
                                           (slower; adds N HTTP calls per page).
                                           [default: no-detail]
```
✅ New `--with-detail / --no-detail` option visible with help text. Default `no-detail` preserves backward-compat.

### Full test suite: `uv run pytest`
```
================ 119 passed, 1 deselected, 4 warnings in 16.80s ================
```
✅ All 119 unit + integration tests pass. 1 deselected = `live` marker (real-network), excluded by default per `pytest.ini_options.addopts`.

### Lint + format: `uv run ruff check . && uv run ruff format --check .`
✅ All checks passed; 44 files already formatted.

## Acceptance criteria walkthrough (from items/001-spec.md)

| Criterion | Verifying test | Status |
|-----------|----------------|--------|
| `DetailConfig` extended; existing YAML loads | `test_detail_config_defaults_to_disabled_and_empty`, `test_loads_testerhome_yaml` | ✅ |
| `testerhome.yaml` populated; `detail.enabled: false` default | `test_loads_testerhome_yaml`, `test_crawl_with_detail_disabled_skips_detail_fetch` | ✅ |
| 3 fixtures created (basic, minified, blocked) | filesystem + integration tests use them | ✅ |
| `_parse_detail` extracts company + salary; identical for minified | `test_parse_detail_extracts_company_and_salary_from_basic_fixture`, `test_parse_detail_extracts_correctly_from_minified_fixture` | ✅ |
| `_parse_detail` returns empty on no-match / disabled | `test_parse_detail_returns_empty_strings_when_no_match`, `test_parse_detail_no_op_when_disabled` | ✅ |
| `_extract_first_label_value` iterates block-level children | exercised by minified-fixture test | ✅ |
| `_enrich_from_detail` recomputes canonical_id only; preserves `id`; don't-clobber on empty; don't-downgrade salary | `test_enrich_fills_company_and_salary_and_recomputes_canonical_id_only`, `test_enrich_no_op_when_detail_empty`, `test_enrich_preserves_listing_salary_when_detail_salary_blank`, `test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable`, `test_enrich_uses_detail_salary_when_listing_was_unparseable` | ✅ |
| `_fetch_classified` refactor; existing listing tests still green | all 9 tests in `tests/sources/test_testerhome.py` pass | ✅ |
| `_enrich_page` runs detail enrichment loop; pre-truncates max_jobs; sleeps before fetch; per-job httpx error degrade; classify non-OK halts | `test_crawl_with_detail_*` four scenarios | ✅ |
| Detail block does not write blob; does not write successful url_cache row | `test_crawl_with_detail_block_converts_to_partial_harvest` (asserts `detail_blob_count == 1`) | ✅ |
| CLI `--with-detail / --no-detail` flag added; overrides via `model_copy` | `test_crawl_help_lists_with_detail_flag` + manual `uv run jma crawl --help` | ✅ |
| 4 integration scenarios all green | all 4 in `test_testerhome_with_detail.py` pass | ✅ |
| Full suite green; ruff clean | `uv run pytest` 119/119, ruff 0 errors | ✅ |

## Live smoke (deferred)

`uv run jma crawl --region Hangzhou --keywords "测试" --max-pages 1 --max-jobs 3 --with-detail -v`
**Not run** — Phase 9 of the plan marks the live smoke as optional ("don't gate the PR on it"). Real-site behaviour is exercised in respx-mocked integration tests; running against the real site requires manual review of the resulting DB rows and could be blocked by anti-bot defenses unrelated to this change.

## Verdict: PASS — all acceptance criteria met; CLI entry-points functional; tests green; lint clean.
