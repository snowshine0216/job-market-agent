# Phase 2 Design — Bing Aggregator (SerpAPI) + `jma view` + TesterHome Retirement

> Implementation spec for `PLAN.md` Phase 2 (revised).
>
> Date: 2026-05-23 · Status: ready for implementation plan
>
> Parent: [PLAN.md](../../../PLAN.md). The original Phase 2 entry
> ("Add randstad.py, bing.py, browser.py + sources status command") is
> superseded by this spec. Rationale and the revised PLAN edits are in §9.
>
> Companion docs:
> [CONTEXT.md](../../../CONTEXT.md) (glossary),
> [Phase 0+1 spec](2026-05-21-phase-0-1-design.md),
> [ADR-0001](../../adr/0001-cross-source-dedup-via-canonical-id.md)
> (cross-source dedup),
> [ADR-0003](../../adr/0003-url-freshness-as-durable-signal.md)
> (URL freshness),
> [ADR-0005 — to be written by this phase](../../adr/0005-bing-aggregator-source-and-snippet-data-quality.md).

---

## 1. Scope

**In scope (this phase)**

1. Retire TesterHome end-to-end — source code, YAML config, source tests, live test, dedicated diagram, README + CLAUDE.md mentions, CLI default flip.
2. Add the **Bing-aggregator source** via SerpAPI (Bing engine). Single source class, multi-site query template, snippet-only by default with optional `--with-detail` enrichment that never halts the crawl on a detail-fetch block.
3. Add `jma view` — a CLI command that renders one self-contained static HTML page (Jinja2) listing every observation in the latest finished run. Sortable client-side via ~30 lines of vanilla JS. No web server.
4. Wipe `data/jobs.db` and `data/raw/testerhome/`. New DB is bootstrapped on first crawl as today.
5. Update PLAN.md, CLAUDE.md, README.md to reflect the SerpAPI-not-Bing-v7 reality and the new shipping surface.
6. Refresh / replace four diagram HTML files in `docs/diagrams/`.
7. Write a new ADR-0005 capturing the snippet-only-by-default policy and the `bing:<host>` source-naming convention.

**Out of scope (deferred)**

- Randstad direct crawler, Playwright fallback (`sources/browser.py`) — volume coverage solved by Bing across CN boards; deferred until a concrete use case justifies them.
- LLM extraction (DeepSeek), `data/skills.yaml`, market & fit reports, `jma run` wrapper — unchanged Phase 3-6 from PLAN.md.
- `jma sources status` health-check — one-source phase makes it premature; revisit when 2+ sources exist.
- `jma view` filtering, multi-run picker, aggregates panel — user explicitly chose minimal table-only variant.
- Direct BOSS Zhipin crawler — its anti-bot stack (sliding captcha, fingerprinting, encrypted API params) is a multi-day yak-shave; covered indirectly via Bing's `site:zhipin.com` snippets.
- Live SerpAPI tests in CI — opt-in `-m live` smoke covers it; CI never burns quota.

## 2. Decisions resolved by this spec

| # | Branch | Decision |
|---|---|---|
| 1 | Why retire TesterHome | Volume too low. As a QA/testing community, "AI agent" searches surface mostly test-automation roles; the AI-engineering sample is too small for meaningful market stats. |
| 2 | Replacement source strategy | Single Bing-aggregator surfacing JDs from BOSS+Lagou+Liepin+51job+Zhilian via SerpAPI's Bing engine. Trades per-row quality (snippet-only baseline) for breadth-of-coverage that exceeds what direct crawls can yield before getting captcha-walled. |
| 3 | Search API provider | SerpAPI (Bing engine). Microsoft's Bing Web Search v7 was retired 2025-08-11; SerpAPI is the closest in-spirit replacement that preserves Bing SERP semantics + strong `site:` operator support. Free tier 100 queries/month is enough for personal-use crawl cadence (~20 crawls/month at 5 SERP pages each). |
| 4 | Source naming | Crawler is `bing`. Each observation's `source` field is `bing:<host>` where `<host>` is the result link's host (e.g. `bing:zhipin.com`, `bing:lagou.com`). One crawl writes N observations across multiple `source` values — schema already supports this. Convention matches [CONTEXT.md "Source"](../../../CONTEXT.md#source). |
| 5 | Per-page vs per-result raw blob | One blob per SerpAPI page (5 SERP pages → 5 gzipped JSON blobs per crawl). Many `Job` rows share the same `raw_payload_ref`. Cheaper disk, fewer files, re-parseable later. |
| 6 | Detail-fetch policy | Default **off**. With `--with-detail`, attempt JD fetch via existing `AsyncHttpClient` + `classify()`. **A detail-fetch block does NOT halt the crawl** (departure from TesterHome's `_enrich_page` behavior). One blocked detail = one row stays snippet-only at `data_quality=0.4`; the SerpAPI page is already in hand and the other results are unaffected. |
| 7 | `data_quality` semantics | Reserved values: `1.0` = full structured-source row (none in Phase 2), `0.9` = bing + successful detail fetch, `0.4` = bing snippet-only or detail-fetch failed. Aggregation rule from PLAN.md (§ Phase 4) stands: salary medians use `data_quality >= 0.7`; top-skills weights linearly by `data_quality`. |
| 8 | Company extraction from snippet | Heuristic-only: small generic regex against `title - company - site_name`. On no match, leave `company=None`. No per-site regex tax; no LLM in Phase 2. `company=None` is a first-class state already (canonical_id tolerates it). |
| 9 | SerpAPI key handling | `SERPAPI_KEY` env var. CLI fails fast — after arg parsing, before opening the DB — if any selected source has `api_key_env` set and the named env var is unset. Error: `missing env var SERPAPI_KEY (required by source 'bing')`. No `python-dotenv` dep — users export it from their shell. |
| 10 | URL cache reuse | The 24h `url_cache` (Phase 1) applies to both SerpAPI page URLs (`https://serpapi.com/search?q=...`) and, when `--with-detail`, the JD URLs. `--no-cache` forces refresh of both. No second cache table. |
| 11 | `jma view` default run | "Latest **finished** run" (`runs.finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1`). A half-finished run would render an empty/misleading table. If no finished run exists, exit non-zero with a clear message. |
| 12 | `jma view` output path | Fixed `data/view.html`, overwritten each invocation. `--out <path>` overrides. `--open` shells out to `open` (macOS) / `xdg-open` (Linux) after writing. |
| 13 | `jma view` template scope | One H1 + one subtitle line + one sortable table. No header card with per-source counts, no run-picker, no aggregates panel. (User explicitly chose the minimal variant.) |
| 14 | Sortable lib for the view page | Hand-written ~30 lines of vanilla JS in an inline `<script>`. Type-aware (numeric for `dq`/`posted_at`, string for the rest). Zero CDN deps; works offline. |
| 15 | New dep | Add `jinja2>=3.1` to `pyproject.toml`. No other deps added or removed. |
| 16 | Existing DB rows | Wipe `data/jobs.db` and `data/raw/testerhome/` as part of the retirement. The 10 existing TesterHome rows don't need to coexist with bing-source rows for any analytical purpose. Document the wipe in the spec; do not script it into the CLI. |
| 17 | Diagram update list | `phase-1-testerhome-crawl.html` deleted + replaced with `phase-2-bing-aggregator-crawl.html`. `plan-phases-workflow.html`, `module-dependency.html`, `database-schema.html` refreshed in place. CLAUDE.md "Workflow charts" triggers already cover this; spec lists the files explicitly to anchor the deliverables checklist. |

## 3. Architecture

### 3.1 Source plug-in

`BingAggregatorSource` implements the existing `JobSource` Protocol — same `name` attribute, same `async crawl(region, keywords, max_pages, max_jobs) -> SourceResult` signature. The pipeline orchestrator in [src/jma/pipeline/crawl.py](../../../src/jma/pipeline/crawl.py) is unchanged. The only new wiring is a factory in `cli.py` and a YAML in `config/sources/bing.yaml`.

```
src/jma/sources/
├── base.py              (unchanged)
├── http.py              (unchanged — used by optional detail-fetch)
├── bing.py              ← NEW
└── (testerhome.py — DELETED)

config/sources/
├── bing.yaml            ← NEW
└── (testerhome.yaml — DELETED)
```

### 3.2 `config/sources/bing.yaml`

```yaml
name: bing
engine: bing                 # serpapi engine key
endpoint: https://serpapi.com/search
api_key_env: SERPAPI_KEY
results_per_query: 50        # serpapi cap; one page per query
target_sites:
  - zhipin.com
  - lagou.com
  - liepin.com
  - 51job.com
  - zhaopin.com
query_template: >
  ({keywords}) ({region_variants})
  ({site_clause}) (招聘 OR hiring OR JD) -inurl:resume
region_aliases:              # inline for Phase 2; move to data/region_aliases.yaml in Phase 3
  Hangzhou: [Hangzhou, 杭州, 杭州市]
rate:
  delay_ms: 800              # gap between SerpAPI page requests AND between detail fetches when --with-detail
  max_retries: 3
  backoff_base_s: 1.0
detail:
  enabled: false             # default off: snippet-only is the v1 contract
content_block_markers: []    # snippet-only path never invokes classify()
```

The `SourceConfig` pydantic model in `sources/base.py` gains the fields needed for this YAML; existing TesterHome-specific fields (`listing.url_template`, `listing.list_item_selector`, etc.) become optional or are split into a sub-model so direct-crawl sources can still load their own YAMLs in the future.

### 3.3 Query construction example

For `--region Hangzhou --keywords "AI agent"`:

```
("AI agent") (Hangzhou OR 杭州 OR 杭州市)
(site:zhipin.com OR site:lagou.com OR site:liepin.com OR site:51job.com OR site:zhaopin.com)
(招聘 OR hiring OR JD) -inurl:resume
```

One SerpAPI call returns up to 50 organic results. `max_pages=N` maps 1:1 to N SerpAPI calls (page 1..N via SerpAPI's `start` param, `start = (page - 1) * results_per_query`), yielding up to `N * 50` results before dedup/region/keyword post-filtering. The CLI's existing `--max-pages 5` default therefore costs 5 SerpAPI queries per crawl, ~20 crawls/month on the free tier. `--max-jobs` truncates the same way as TesterHome.

### 3.4 SerpAPI result → `Job` mapping

```python
Job(
    id=job_id(source=f"bing:{host}", internal_id=parsed_path_id_or_None, ...),
    canonical_id=canonical_id(title=cleaned_title, company=heuristic, city=region),
    source=f"bing:{host}",                       # e.g. "bing:zhipin.com"
    source_internal_id=parsed_id,                # zhipin job id from URL when extractable
    title=cleaned(result["title"]),
    title_raw=result["title"],
    company=_heuristic_company_from_snippet(result["snippet"]),  # None when uncertain
    location=Location(country="CN", city=region, district=None, work_mode=UNKNOWN),
    salary=parse_salary(result["snippet"]) or Salary(parsed=False, raw=""),
    experience=parse_experience(result["snippet"]),
    posted_at=parse_iso(result.get("date")) if "date" in result else None,
    fetched_at=now_utc(),
    url=result["link"],
    raw_payload_ref=blob_ref_for_serpapi_json,   # one blob per SerpAPI page
    data_quality=0.4,                            # snippet-only baseline
)
```

`Location.city` is set to the user-supplied region directly when `region != ""`; when `--region ""` (filter disabled), `Location.city = None` because we genuinely don't know the workplace from a SERP snippet. `district` stays `None` (we don't probe snippets for districts in Phase 2). When the optional detail fetch succeeds and the JD page exposes a city/district, those win over the listing-time defaults — same merge contract as TesterHome's `_enrich_from_detail`: detail wins, but never clobbers a known value with an empty one.

`source_internal_id` is best-effort: try to pull a numeric path segment via per-host URL regex (`/job_detail/<id>.html` on zhipin, `/job/<id>.html` on liepin, etc.). On no match, fall back to the `job_id` content hash already handled by `domain/dedup.py:job_id()`.

### 3.5 Detail-fetch outcomes (when `--with-detail`)

| Detail-fetch outcome | `data_quality` | `url_status` | Behavior |
|---|---|---|---|
| 200 + classify=OK | **0.9** | `live` | Detail-enriched fields (company/salary/JD text); fall back to snippet for anything still empty |
| 200 + classify=BLOCKED | **0.4** | `unknown` | Snippet-only Job; do NOT write blob; do NOT poison URL cache |
| 404 / 410 | **0.4** | `gone` | Snippet-only Job; tag URL as gone |
| 429 / 5xx / network error | **0.4** | `unknown` | Snippet-only Job; preserve prior signal (ADR-0003) |
| Other 4xx | **0.4** | `unknown` | Snippet-only Job |

**Critical:** none of these outcomes halt the crawl. This is the deliberate departure from TesterHome's `_enrich_page` behavior — losing one JD fetch is one row's data-quality drop, not a crawl-ender, because the SerpAPI page is already in hand.

### 3.6 `jma view` command

CLI surface:

```bash
uv run jma view                       # → data/view.html (latest finished run)
uv run jma view --open                # → also open in browser
uv run jma view --run <id>            # → render a specific run (full hex id, no prefix matching)
uv run jma view --out /tmp/x.html     # → custom output path
```

Flag interactions:
- `--out PATH` overrides the default output. `--open` then opens whichever path was written (the override or `data/view.html`).
- `--run UNKNOWN_ID` → exit non-zero with `no run <id> in <db_path>`.
- `--run <id>` against an unfinished run (no `finished_at`) → exit non-zero with `run <id> is not finished; nothing to render`.
- No `--run` and no finished runs in the DB → exit non-zero with `no finished runs in <db_path>; run 'jma crawl ...' first`.

Run-id matching is exact (full hex). Prefix matching is a later convenience if it shows up as a need.

File layout:

```
src/jma/report/                ← NEW module
├── __init__.py
├── view.py                    # pure: build_view_context(run, jobs) -> dict
└── templates/
    └── view.html.j2           # single Jinja2 template
```

Pure/effect split (per project rules):

- `report/view.py` is **pure**: `build_view_context(run_row, job_rows) -> dict` returns the data structure the template renders.
- `cli.py view` does the effects: opens DB, queries latest finished run + its jobs (via existing `run_jobs` join), calls `build_view_context`, renders the template, writes the file, optionally shells out to `open`/`xdg-open`.
- `storage/db.py` gains two helpers: `latest_finished_run(conn) -> Run | None` and `jobs_for_run(conn, run_id) -> list[Job]`. They return frozen pydantic models; SQL stays inside.

Template rendering (one Jinja2 file, ~80 lines):

```
┌────────────────────────────────────────────────────────┐
│  jma view — run <id-prefix>...                         │
│  <region> · <keywords> · <started_at> · n=<count>      │
├────────────────────────────────────────────────────────┤
│  title │ company │ city │ salary_raw │ posted_at │ src │ url │ blob │ dq │
│  ─────────────────────────────────────────────────────  │
│  <sortable table, all observations from the run>       │
└────────────────────────────────────────────────────────┘
```

Cell rendering:
- `title` truncates at 60 chars with full text in `title=` tooltip; same for `company`.
- `url` is a clickable `<a href>`; `blob` is a clickable `file://` link to the gzipped blob (browsers don't auto-decompress; the link gets the user to the file).
- `dq` shows numeric value (0.4 / 0.9 / 1.0) so the user can visually grok per-row quality.
- Empty cells render as a single em-dash.
- Inline CSS (~30 lines) + inline `<script>` (~30 lines) for sort. No external requests.

### 3.7 Unchanged components

`pipeline/crawl.py`, `storage/db.py` (schema), `storage/blobs.py`, `storage/cache.py`, all of `domain/`. The 24h URL cache applies as-is. Blockage classifier only runs on the optional detail-fetch path in `bing`.

## 4. Schema and migration

**Zero column changes.** Existing `jobs` table already has `source TEXT`, `source_internal_id TEXT`, `data_quality REAL`, `url_status TEXT`, `url_last_checked_at TEXT`, `raw_payload_ref TEXT`. The bing-aggregator uses all of them as-designed.

**Wipe `data/jobs.db` and `data/raw/testerhome/`** as a manual step documented in the spec. No CLI command to do it. New DB is created on first crawl via the existing `executescript(_DDL)` bootstrap.

## 5. File changes

### 5.1 Deletions

```
src/jma/sources/testerhome.py
config/sources/testerhome.yaml
tests/sources/test_testerhome.py
tests/sources/test_testerhome_detail.py
tests/sources/test_testerhome_with_detail.py
tests/live/test_testerhome_live.py
docs/diagrams/phase-1-testerhome-crawl.html
data/jobs.db                                   (gitignored, manual)
data/raw/testerhome/                           (gitignored, manual)
```

### 5.2 Conditional deletions (grep-first)

```
tests/sources/test_detail_config_defaults.py
tests/sources/test_url_freshness.py
```

Both predate this phase and may be TesterHome-coupled. The plan **must** grep each for TesterHome-specific fixtures before deciding:

- If the test only exercises TesterHome's HTML shape, delete.
- If it exercises generic source-config or url-freshness logic via TesterHome as a fixture vehicle, port it to `bing` fixtures rather than delete.

### 5.3 Additions

```
src/jma/sources/bing.py
src/jma/report/__init__.py
src/jma/report/view.py
src/jma/report/templates/view.html.j2
config/sources/bing.yaml
docs/diagrams/phase-2-bing-aggregator-crawl.html
docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md

tests/sources/test_bing.py
tests/sources/test_bing_with_detail.py
tests/sources/test_bing_company_heuristic.py
tests/live/test_bing_live.py
tests/report/__init__.py
tests/report/test_view.py
tests/report/test_view_template.py
tests/cli/test_view.py
```

### 5.4 Edits

| File | Change |
|---|---|
| [src/jma/cli.py](../../../src/jma/cli.py) | Remove `TesterHomeSource` import; remove TesterHome branch from `_factory_for`; add `BingAggregatorSource` factory branch; flip `--source` default to `["bing"]`; add new `view` subcommand |
| [src/jma/sources/base.py](../../../src/jma/sources/base.py) | Adjust `SourceConfig` so direct-crawl-specific fields (`listing.*`, `detail.*`) and aggregator-specific fields (`engine`, `endpoint`, `api_key_env`, `target_sites`, `query_template`, `region_aliases`) can coexist. Likely split into `direct: DirectCrawlConfig \| None` + `aggregator: AggregatorConfig \| None` discriminated by `engine` field presence. |
| [src/jma/storage/db.py](../../../src/jma/storage/db.py) | Add `latest_finished_run(conn) -> Run \| None` and `jobs_for_run(conn, run_id) -> list[Job]`. Domain models return; SQL stays internal. |
| [pyproject.toml](../../../pyproject.toml) | Add `jinja2>=3.1` to `dependencies` |
| [README.md](../../../README.md) | Replace "first shipping source is TesterHome" framing; replace example output blocks with bing examples; flip `--source` default in options table; refresh Phase status badge to "Phase 0 + Phase 1 + Phase 2"; add "Verify a crawl" subsection covering `jma view` |
| [PLAN.md](../../../PLAN.md) | See §9 below for exact edits |
| [CLAUDE.md](../../../CLAUDE.md) | Replace "Phase 1 ships only the TesterHome crawler vertical slice" with the post-Phase-2 reality; refresh "Source plug-in contract" example to use `bing` and the `bing:<host>` naming; add `report/` to the architecture tree |
| [CONTEXT.md](../../../CONTEXT.md) | Audit for `testerhome` mentions; the existing "Source" section already documents the `bing:<host>` pattern as the aggregator example, so no rewrite needed there. Glossary is largely source-agnostic and stays. |
| `docs/diagrams/plan-phases-workflow.html` | Update Phase 2 box to "Bing aggregator + view page"; advance current-slice marker |
| `docs/diagrams/module-dependency.html` | Replace `sources/testerhome.py` node with `sources/bing.py`; add `cli.py → report/view.py → Jinja2` edges |
| `docs/diagrams/database-schema.html` | No column changes. Refresh annotations: `data_quality` graduates from "always 1.0" to "0.4 snippet / 0.9 detail-enriched"; mention `source` LIKE `'bing:%'` pattern; bump ADR list to include ADR-0005 |

## 6. Tests (TDD-first)

All tests written **before** the implementation they exercise. Red-green-refactor.

**`tests/sources/test_bing.py`** — pure-ish:
- Fixture SerpAPI JSON response (saved from a one-time real call to `tests/fixtures/serpapi_bing_hangzhou_ai_agent.json`) parsed into expected `Job` list (snippet-only).
- Asserts `source == "bing:<host>"` derivation from `link`.
- Asserts `source_internal_id` extracted via per-host URL regex when matched, falls back to `None`.
- Asserts `data_quality == 0.4` for every row.
- Asserts the per-page raw blob is written once and N rows share its `raw_payload_ref`.
- Asserts region + keyword filtering applies post-fetch the same way as TesterHome.

**`tests/sources/test_bing_with_detail.py`** — covers the optional detail-fetch matrix:
- One fixture JD body returning 200 + classify=OK → `data_quality=0.9`, `url_status=LIVE`, enriched company/salary.
- One returning 200 + classify=BLOCKED (captcha marker) → row stays snippet-only, blob NOT written, **next result still attempted**.
- One returning 404 → snippet-only, `url_status=GONE`.
- One returning 429 → snippet-only, `url_status` preserved.
- One raising `httpx.HTTPError` → snippet-only, next result still attempted.
- Asserts the crawl produces N rows for N input results regardless of per-detail outcomes (no halt).

**`tests/sources/test_bing_company_heuristic.py`** — parameterised over real-shaped titles/snippets:
- `("AI Agent 工程师 - 阿里巴巴 - BOSS直聘", "杭州 · …")` → `company == "阿里巴巴"`
- `("AI Engineer | NetEase", "Hangzhou · …")` → `company == "NetEase"`
- `("AI Agent 后端", "杭州 余杭 · 25-50K · …")` → `company is None`

**`tests/live/test_bing_live.py`** — opt-in `@pytest.mark.live`:
- One real SerpAPI call with `site:zhipin.com` clause.
- Asserts ≥1 result whose `link` host matches `zhipin.com` (validates the `site:` operator works as expected through SerpAPI).

**`tests/report/test_view.py`** — pure:
- Fixture `Run` + 3 fixture `Job`s → expected context dict (columns, ordering, value formatting like `data_quality=0.4`, em-dash for empty cells, truncated titles).

**`tests/report/test_view_template.py`** — render template against context:
- Asserts via `selectolax` (already a dep): correct number of `<tr>` rows, sortable-by class on `<th>`s, `<a href>` on url + blob cells, run-id prefix in `<h1>`, no `<script src=...>` (offline guarantee).

**`tests/cli/test_view.py`** — Typer `CliRunner`:
- Empty DB → exit code non-zero + `no finished runs in <db_path>` message.
- DB with one finished run → file at `data/view.html` exists, contains run-id prefix, contains "n=<count>".
- `--run <unknown_id>` → exit code non-zero + clear message.

**Test data:**
- `tests/fixtures/serpapi_bing_hangzhou_ai_agent.json` — one captured SerpAPI envelope, hand-curated to cover 5 hosts and 50 results.
- `tests/fixtures/bing/detail_*.html` — one per outcome type (ok, blocked, 404, 429, error).

## 7. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| SerpAPI's `site:` operator behavior differs from native Bing SERPs | Medium | Live test (`tests/live/test_bing_live.py`) asserts host match. Run once during dev; opt-in marker keeps CI off the network. |
| Snippet quality varies wildly per board (zhipin short, liepin richer) | Medium | `data_quality=0.4` already discounts these in aggregations. Snippet IS the data in Phase 2; no fix needed. |
| Heuristic-B company extraction leaves `company=None` on majority of rows | High (by design) | Acceptable; `canonical_id` tolerates None; Phase 3 LLM extraction backfills. |
| SerpAPI quota exhaustion mid-development (100/mo free) | Low-Medium | 24h `url_cache` covers SERP URLs; `--no-cache` opt-out for force-refresh. Document the $75/mo dev tier in README if hitting the wall. |
| Bing's `site:` ranking under-represents BOSS vs. Liepin | Medium | YAML-configurable `target_sites` ordering. Per-site result-count balancing is a Phase 2.1 follow-up if it shows up in practice. |
| `jma view` against a wiped DB shows nothing useful until first crawl | Trivial | Exit message: `no finished runs in <db_path>; run 'jma crawl ...' first`. |
| TesterHome retirement deletes `test_url_freshness.py` if it was actually generic | Low | §5.2 grep-first policy; port to bing fixtures rather than delete if generic. |
| Diagram drift if author forgets a `.html` file | Low | CLAUDE.md "Workflow charts" section already binds diagram updates to triggers; this spec lists the diagram files in §5.3 / §5.4 deliverables. |
| `SourceConfig` refactor (§5.4) breaks unrelated code | Low | All callers are in this repo; covered by existing tests + the new bing tests. |

## 8. Acceptance criteria (the demo)

```
$ export SERPAPI_KEY=...
$ uv run jma crawl --region Hangzhou --keywords "AI agent"
run_id        : <hex>
region        : Hangzhou
keywords      : AI agent
sources:
  bing       : ok    pages=5  jobs=180   elapsed=8.4s
written       : 180 observations to data/jobs.db

$ uv run jma view --open
wrote data/view.html (run <hex-prefix>, 180 observations)
# → browser opens, table sorts on click, you eyeball-verify the crawl
```

Everything in §§1-7 is in service of this two-command flow working cleanly.

## 9. PLAN.md edits

Concrete diff plan against the current PLAN.md:

| Section | Change |
|---|---|
| §1 row 2 (v1 sources) | Replace "Lean: TesterHome + Randstad + Bing-aggregator (pluggable `JobSource`)" with "Lean: Bing-aggregator (SerpAPI) via pluggable `JobSource`. TesterHome retired in Phase 2 (volume too low for AI-eng market stats); Randstad deferred." |
| §1 row 4 (Search API) | Replace "Bing Web Search v7" with "SerpAPI (Bing engine; native Bing v7 retired 2025-08-11)" |
| §3 (Module layout) | Remove `testerhome.py`, `randstad.py`, `browser.py` from the tree; add `bing.py`; add `report/view.py` + `report/templates/view.html.j2` |
| §4 Phase 2 heading + body | Replace the Randstad/Bing/Playwright narrative with the three-part Phase 2: (a) retire TesterHome, (b) add Bing-aggregator via SerpAPI, (c) add `jma view`. Keep case 2.A (Bing query construction) — still applicable. Drop case 2.B (Randstad variants) — deferred. |
| §5 Risks | Add: "SerpAPI rate-limit (100/mo free) — mitigation: tight default `max_pages`; cache SERP responses for 24h same as JD URLs." Add: "PLAN intent of cross-board breadth depends on SerpAPI's `site:` operator behavior on each board — verify against fixture before shipping." |
| §6 Open items | Move Randstad / Playwright / direct-BOSS from Phase 2 to "deferred to a later phase or v1.1 if justified" |

## 10. New ADR

**`docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md`** — captures:

- The `bing:<host>` source-naming convention (already implied by CONTEXT.md but never formally decided).
- The snippet-only-by-default policy and the `data_quality=0.4` baseline.
- The "no-halt-on-detail-block" rule that departs from TesterHome's listing-page halt semantics, and why (the SerpAPI page is already in hand).
- The decision to use SerpAPI as the SERP provider given Bing v7's retirement, and what triggers reconsideration (cost, blocked, alternative emerges).

---

*End of spec. Next step on approval: writing-plans skill produces a per-task implementation plan covering the deletions, the bing source, the view command, the doc/diagram refreshes, and the new ADR.*
