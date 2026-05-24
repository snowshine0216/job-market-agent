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
2. Add the **Bing-aggregator source** via SerpAPI (Bing engine). Single source class, multi-site query template, **snippet-only — no detail-fetch in this phase**. The snippet is mapped into the structured columns it already covers (`title`, `posted_at`, `salary`, `experience`) and the raw snippet text is stored in `description_text` as Phase 3's LLM-extraction input. Detail-fetch enrichment is deferred to Phase 2.1; see Out of scope below for the trigger condition.
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
- **Phase 2.1: detail-fetch enrichment for Bing.** Originally planned as an optional `--with-detail` flag in this phase. Deferred because every target board (zhipin / lagou / liepin / 51job / zhaopin) is exactly the set whose anti-bot stack we explicitly defer as out of scope for direct crawling, so most detail fetches would return `BLOCKED` / `429` for no Job-row gain — paying ~50-150 HTTP calls per crawl for a `data_quality=0.4` row that snippet-only already produces. **Trigger to re-open:** a live SerpAPI sample where at least one target board's detail pages return useful 200s (i.e. evidence that the anti-bot is *not* uniform across the target set). When that happens, ADR-0005 grows a "no-halt-on-detail-block" clause and `bing.py` gains an `--with-detail`-style code path; the column footprint (`url_status`, `url_last_checked_at`, `data_quality=0.9`) is already in place.

## 2. Decisions resolved by this spec

| # | Branch | Decision |
|---|---|---|
| 1 | Why retire TesterHome | Volume too low. As a QA/testing community, "AI agent" searches surface mostly test-automation roles; the AI-engineering sample is too small for meaningful market stats. |
| 2 | Replacement source strategy | Single Bing-aggregator surfacing JDs from BOSS+Lagou+Liepin+51job+Zhilian via SerpAPI's Bing engine. Trades per-row quality (snippet-only baseline) for breadth-of-coverage that exceeds what direct crawls can yield before getting captcha-walled. |
| 3 | Search API provider | SerpAPI (Bing engine). Microsoft's Bing Web Search v7 was retired 2025-08-11; SerpAPI is the closest in-spirit replacement that preserves Bing SERP semantics + strong `site:` operator support. Free tier 100 queries/month is enough for personal-use crawl cadence (~20 crawls/month at 5 SERP pages each). |
| 4 | Source naming | Crawler is `bing`. Each observation's `source` field is `bing:<host>` where `<host>` is the **matched `target_sites` entry** (e.g. `bing:zhipin.com`, `bing:lagou.com`) — not the raw URL `netloc`. This collapses `www.zhipin.com`, `m.zhipin.com`, `app.zhipin.com` etc. to one source value so [ADR-0001](../../adr/0001-cross-source-dedup-via-canonical-id.md) cross-source dedup and `WHERE source = 'bing:zhipin.com'` queries both work. Results whose host doesn't match any `target_sites` entry are dropped (with a debug log + a count surfaced in `SourceResult.reason`) so the universe of `source` values stays bounded by the YAML. Convention matches [CONTEXT.md "Source"](../../../CONTEXT.md#source). |
| 5 | Per-page vs per-result raw blob | One blob per SerpAPI page (5 SERP pages → 5 gzipped JSON blobs per crawl). Many `Job` rows share the same `raw_payload_ref`. Cheaper disk, fewer files, re-parseable later. |
| 6 | Detail-fetch policy | **No detail-fetch in Phase 2.** Snippet-only is the only mode. The raw snippet is stored in `description_text` as Phase 3's LLM-extraction input. Detail-fetch is a deferred Phase 2.1 line item — see §1 "Out of scope" for the trigger condition (live evidence that some target board's detail pages aren't anti-bot-walled). |
| 7 | `data_quality` semantics | **In Phase 2, every Bing row is `0.4`** (snippet-only). Reserved values used by later phases: `1.0` = full structured-source row (no source in Phase 2 emits this), `0.9` = Bing + successful detail-fetch (reserved for Phase 2.1), `0.7` = LLM-enriched (reserved for Phase 3). The aggregation rule from PLAN.md (§ Phase 4) — salary medians use `data_quality >= 0.7`, top-skills weights linearly — stands and is forward-compatible: in Phase 2 it filters every Bing row out of salary medians, which is the right outcome until a higher-confidence row class exists. |
| 8 | Company extraction from title | Heuristic-only: generic delim-split on `title` against `[|\-_]`. For 3-part titles (`role DELIM company DELIM site_tail`), the middle segment is the company. For 2-part titles (`role DELIM segment_2`), use the per-host `site_names` YAML anchor: if `segment_2` matches the matched host's `site_name`, drop it and return `None`; otherwise treat `segment_2` as the company (handles English titles like `"AI Engineer \| NetEase"`). On 1-part titles, return `None`. Truly per-site *snippet* regexes remain forbidden — the `site_names` map is one constant string per host, not a parser per host, and is the same per-host-in-YAML pattern as `id_patterns`. Phase 3 LLM extraction reads `description_text` and is the safety net for rows the heuristic gets wrong. `company=None` is a first-class state already (canonical_id tolerates it). |
| 9 | SerpAPI key handling | `SERPAPI_KEY` env var. CLI fails fast — after arg parsing, before opening the DB — if any selected source has `api_key_env` set and the named env var is unset. Error: `missing env var SERPAPI_KEY (required by source 'bing')`. No `python-dotenv` dep — users export it from their shell. |
| 10 | URL cache reuse | The 24h `url_cache` (Phase 1) applies to SerpAPI page URLs (`https://serpapi.com/search?q=...`) — the only URLs Bing fetches in Phase 2. `--no-cache` forces refresh. No second cache table. (When Phase 2.1 detail-fetch lands, the same cache covers JD URLs too.) |
| 11 | `jma view` default run | "Latest **finished** run" (`runs.finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1`). A half-finished run would render an empty/misleading table. If no finished run exists, exit non-zero with a clear message. |
| 12 | `jma view` output path | Fixed `data/view.html`, overwritten each invocation. `--out <path>` overrides. `--open` shells out to `open` (macOS) / `xdg-open` (Linux) after writing. |
| 13 | `jma view` template scope | One H1 + one subtitle line + one sortable table. No header card with per-source counts, no run-picker, no aggregates panel. (User explicitly chose the minimal variant.) |
| 14 | Sortable lib for the view page | Hand-written ~30 lines of vanilla JS in an inline `<script>`. Type-aware (numeric for `dq`/`posted_at`, string for the rest). Zero CDN deps; works offline. |
| 15 | New dep | Add `jinja2>=3.1` to `pyproject.toml`. No other deps added or removed. |
| 16 | Existing DB rows | Wipe `data/jobs.db` and `data/raw/testerhome/` as part of the retirement. The 10 existing TesterHome rows don't need to coexist with bing-source rows for any analytical purpose. Document the wipe in the spec; do not script it into the CLI. |
| 17 | `raw_payload_ref` per-Run vs latest | Promote `raw_payload_ref` to a per-observation-per-run column on `run_jobs`. The existing `jobs.raw_payload_ref` stays as latest-seen (cheap for aggregation paths reading `jobs` directly); `jobs_for_run` reads from `run_jobs.raw_payload_ref` to hydrate `Job.raw_payload_ref` with the blob captured *during that specific Run*. Without this, `jma view --run <old_id>` would silently link to a newer blob than the row was originally observed with — the exact misalignment Phase 2's new view feature exposes. The §2 row 16 DB wipe makes the schema change migration-free. |
| 18 | Diagram update list | `phase-1-testerhome-crawl.html` deleted + replaced with `phase-2-bing-aggregator-crawl.html`. `plan-phases-workflow.html`, `module-dependency.html`, `database-schema.html` refreshed in place — the latter now shows `run_jobs.raw_payload_ref` per row 17. CLAUDE.md "Workflow charts" triggers already cover this; spec lists the files explicitly to anchor the deliverables checklist. |

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
id_patterns:                 # host (must be a target_sites entry) → capture-group-1 regex for source_internal_id
  zhipin.com: '/job_detail/(\d+)\.html'
  liepin.com: '/job/(\d+)\.html'
  # lagou.com / 51job.com / zhaopin.com left unmapped on purpose — their URL schemes vary too
  # much in current Bing results to commit a stable regex. Result: source_internal_id stays None
  # on those hosts and Job.id falls through to dedup.py's content-hash branch. Grow this map only
  # when a stable pattern has been verified against the live fixture.
site_names:                  # host → board's Chinese-language site name; used as the heuristic's site-name anchor
  zhipin.com: BOSS直聘       # so "AI Agent | BOSS直聘" yields company=None (not "BOSS直聘")
  lagou.com: 拉勾招聘
  liepin.com: 猎聘
  51job.com: 前程无忧
  zhaopin.com: 智联招聘
query_template: >
  ({keywords}) ({region_variants})
  ({site_clause}) (招聘 OR hiring OR JD) -inurl:resume
region_aliases:              # inline for Phase 2; move to data/region_aliases.yaml in Phase 3
  Hangzhou: [Hangzhou, 杭州, 杭州市]
# Fallback when --region <X> has no entry in this map: variants = [X] (identity).
# bing.py logs once at INFO ("region 'X' has no aliases; using identity fallback") so the
# operator sees the coverage gap and can grow this map. --region "" → no {region_variants}
# clause in the query at all; the post-fetch region filter is also a no-op.
rate:
  delay_ms: 800              # gap between SerpAPI page requests
  max_retries: 3
  backoff_base_s: 1.0
```

The `SourceConfig` pydantic model in `sources/base.py` is **replaced**, not extended: with TesterHomeSource being deleted in this same phase, the TesterHome-shaped sub-models (`ListingConfig`, `DetailConfig`, `content_block_markers`, `known_good_list_selector`, `base_url`) lose their only consumer. We delete them along with the source. The new `SourceConfig` is Bing-shaped: `name`, `engine`, `endpoint`, `api_key_env`, `target_sites`, `id_patterns`, `query_template`, `region_aliases`, `rate`. A discriminated-union shape (`direct: DirectCrawlConfig | None` + `aggregator: AggregatorConfig | None`) is deferred until a second source ships that genuinely needs both branches — YAGNI today, easy to add when needed.

### 3.3 Query construction example

For `--region Hangzhou --keywords "AI agent"`:

```
("AI agent") (Hangzhou OR 杭州 OR 杭州市)
(site:zhipin.com OR site:lagou.com OR site:liepin.com OR site:51job.com OR site:zhaopin.com)
(招聘 OR hiring OR JD) -inurl:resume
```

One SerpAPI call returns up to 50 organic results. `max_pages=N` maps 1:1 to N SerpAPI calls (page 1..N via SerpAPI's `start` param, `start = (page - 1) * results_per_query`), yielding up to `N * 50` results before dedup/region/keyword post-filtering. The CLI's existing `--max-pages 5` default therefore costs 5 SerpAPI queries per crawl, ~20 crawls/month on the free tier. `--max-jobs` truncates the same way as TesterHome.

**Edge cases in the template:**

- `--region <X>` where `X` has no entry in `region_aliases`: identity fallback (`variants = [X]`). Query becomes `(... ) (X) (site_clause) (...)` — coverage is degraded for CJK markets where the Roman name alone won't find the Chinese-titled posting, and `bing.py` logs once at INFO so the operator knows to grow the YAML.
- `--region ""` (filter disabled): the `{region_variants}` group is omitted from the rendered template, yielding `({keywords}) ({site_clause}) (招聘 OR hiring OR JD) -inurl:resume`. The post-fetch region filter is a no-op for this case (the existing `_filter_region` short-circuits on empty input).
- `--keywords ""` is not a separately documented case; the CLI requires at least one `--keywords` value via Typer's required-option, so we can rely on at least one non-empty phrase.

### 3.4 SerpAPI result → `Job` mapping

```python
Job(
    id=job_id(source=f"bing:{host}", internal_id=parsed_path_id_or_None, ...),
    canonical_id=canonical_id(title=cleaned_title, company=heuristic, city=region),
    source=f"bing:{host}",                       # host = matched target_sites entry, see §2 row 4
    source_internal_id=parsed_id,                # zhipin job id from URL when extractable
    title=cleaned(result["title"]),
    title_raw=result["title"],
    company=_heuristic_company_from_title(                       # None when uncertain — see §2 row 8
        result["title"], cfg.site_names.get(matched_host)
    ),
    location=Location(country="CN", city=None, district=None, work_mode=UNKNOWN),
    salary=parse_salary(result["snippet"]) or Salary(parsed=False, raw=""),
    experience=parse_experience(result["snippet"]),
    posted_at=parse_iso(result.get("date")) if "date" in result else None,
    fetched_at=now_utc(),
    url=result["link"],
    raw_payload_ref=blob_ref_for_serpapi_json,   # one blob per SerpAPI page
    data_quality=0.4,                            # snippet-only baseline; sole value in Phase 2
    description_text=result.get("snippet", ""),  # raw snippet text → Phase 3 LLM-extraction input
)
```

`Location.city` is always `None` for snippet-only rows. We do **not** probe SERP snippets for city tokens in Phase 2, and we deliberately do **not** stamp the user-supplied `--region` onto `city` — per [CONTEXT.md "Location"](../../../CONTEXT.md#location), `city` is the workplace and is never a best-guess fallback. The post-fetch region filter (`_filter_region` in the existing source code) already keeps rows whose `city` is `None`, so the SERP-side `site:` + region-in-query clause does the geographic narrowing and the post-filter is a permissive safety net. `canonical_id` therefore stays `sha1(title|company|None)` — stable across `--region` re-crawls of the same posting and across [[Source]]s. `district` stays `None` for the same reason. When the optional detail fetch succeeds and the JD page exposes a city/district, those win over the snippet-time `None` — same merge contract as TesterHome's `_enrich_from_detail`: detail wins, but never clobbers a known value with an empty one.

> Tension already on the radar: a later snippet-only re-crawl of a row that was previously detail-enriched still triggers `excluded.location_city = NULL` in the upsert and would wipe the earned city signal. This is the same overwrite-on-listing-crawl problem [ADR-0003](../../adr/0003-url-freshness-as-durable-signal.md) flags for "merge by confidence" across `company`/`salary`/etc., not new to Phase 2. Out of scope here — solve when we have evidence it bites.

`source_internal_id` is best-effort: look up `cfg.id_patterns.get(matched_host)` and, if a regex is configured, try to capture group 1 from the URL path. **On no regex configured, or on a regex miss, `source_internal_id` stays `None`** — exactly the same first-class state TesterHome uses when `/topics/(\d+)` doesn't match. `Job.id` then falls through to `dedup.py:job_id()`'s `title|company|city` content-hash branch automatically; we do **not** stamp that hash into the `source_internal_id` column. The asymmetry vs the company-extraction policy (which forbids per-site regexes) is intentional: URL path schemes are stable vendor convention and change rarely, while snippet formats are noisy and Phase 3's LLM extraction will replace any per-site snippet regex anyway. See ADR-0005 for the rationale.

### 3.5 `jma view` command

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

- `report/view.py` is **pure**: `build_view_context(run_row, job_rows, data_root_abs: Path) -> dict` returns the data structure the template renders. `data_root_abs` is the absolute path of the data root (CLI passes `Path(data_root).resolve()`); the context puts it under the `data_root_abs` key so the template can render blob `<a href>`s as absolute `file://{data_root_abs}/{raw_payload_ref}` URIs that survive `--out` writes to arbitrary locations (`/tmp/x.html`, a cloud-synced folder, etc.). Locality assumption: those `file://` links are valid only on the machine that ran the crawl — cross-machine viewing of `view.html` is explicitly a non-goal (no web server, single user, no auth).
- `cli.py view` does the effects: opens DB, queries latest finished run + its jobs (via the `run_jobs` join), calls `build_view_context(run, jobs, data_root.resolve())`, renders the template, writes the file, optionally shells out to `open`/`xdg-open`.
- `storage/db.py` gains two helpers: `latest_finished_run(conn) -> Run | None` and `jobs_for_run(conn, run_id) -> list[Job]`. They return frozen pydantic models; SQL stays inside. `jobs_for_run` joins `run_jobs` and **reads `run_jobs.raw_payload_ref` into the returned `Job.raw_payload_ref` field** (per §2 row 17), so the view links to the blob captured *during that specific Run*, not the latest one stamped onto the `jobs` row by a later re-observation.

> **Scope of the per-Run split.** Only `raw_payload_ref` moves to `run_jobs` in Phase 2. `description_text` (and `company`, `salary`, `posted_at`, etc.) stays on `jobs` with latest-wins upsert semantics — Bing's snippet content drifts as the index updates and the *latest* snippet is generally an improvement for Phase 3 LLM extraction. The cosmetic consequence: `jma view --run <old_id>` shows the old Run's blob link but the latest crawl's snippet text. Acceptable for Phase 2; revisit when (and if) a future "merge by confidence" ADR generalises the per-Run pattern to other fields.
- **Row ordering lives in SQL**, not in `build_view_context`. `jobs_for_run` returns rows pre-sorted `ORDER BY posted_at DESC NULLS LAST, fetched_at DESC` so the freshest postings land at the top of the initial render (`fetched_at DESC` is the deterministic tiebreaker among rows with `posted_at IS NULL` — Bing's `date` field resolves for only ~70-80% of results, so a stable secondary sort matters). `build_view_context` then preserves the list order; tests pass pre-ordered fixtures to exercise the template without touching the DB. SQLite's `NULLS LAST` syntax requires 3.30+ (2019); a one-line comment in `db.py` notes the dependency.

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
- `url` is a clickable `<a href="{{ job.url }}">` (already an `https://` URL — no path computation).
- `blob` is a clickable `<a href="file://{{ data_root_abs }}/{{ job.raw_payload_ref }}">` — an absolute `file://` URI built from the resolved `data_root` and the per-Run blob ref. Browsers don't auto-decompress `.gz`; the link gets the user to the file. The displayed text is the last 16 chars of `raw_payload_ref` (matches `_sha1_short` length, keeps the column narrow).
- `dq` shows numeric value (0.4 / 0.9 / 1.0) so the user can visually grok per-row quality.
- Empty cells render as a single em-dash.
- Inline CSS (~30 lines) + inline `<script>` (~30 lines) for sort. No external requests. Sort behaviour is single-column, two-state: a click on any column header flips the order asc ↔ desc; clicking a different column starts that column at asc. The initial page render shows the SQL-side order (`posted_at` DESC); a user can re-anchor to any column by clicking. Numeric comparator for `dq`; ISO-string lexicographic comparator for `posted_at` (ISO datetimes sort correctly as strings — no `Date.parse` needed); string comparator for the rest.

### 3.6 Unchanged components

`pipeline/crawl.py`, `storage/db.py` (schema), `storage/cache.py`, all of `domain/`. `storage/blobs.py` gains an optional `suffix` argument (default `".html.gz"`) so the bing source can write SerpAPI JSON as `.json.gz` — see §5.4. The 24h URL cache applies as-is, scoped to SerpAPI page URLs (the only URLs Bing fetches in Phase 2). The blockage classifier is **not** invoked by `bing` in Phase 2 (snippet-only path); the classifier lands back in play if Phase 2.1 detail-fetch ships.

## 4. Schema and migration

**One additive column on `run_jobs`.** The existing `jobs` table is unchanged — `source TEXT`, `source_internal_id TEXT`, `data_quality REAL`, `url_status TEXT`, `url_last_checked_at TEXT`, `raw_payload_ref TEXT` are all used as-designed by the bing-aggregator. `run_jobs` gains `raw_payload_ref TEXT NOT NULL` (per §2 row 17) so each `(run_id, job_id)` pair carries the blob snapshot from that specific observation. Aggregation paths reading `jobs.raw_payload_ref` directly continue to see latest-seen; `jobs_for_run` reads from `run_jobs.raw_payload_ref` to get the per-Run snapshot.

**Wipe `data/jobs.db` and `data/raw/testerhome/`** as a manual step documented in the spec. No CLI command to do it. The wipe makes the new `run_jobs.raw_payload_ref` column migration-free — new DB is created on first crawl via the existing `executescript(_DDL)` bootstrap.

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
tests/sources/test_bing_company_heuristic.py
tests/live/test_bing_live.py
tests/storage/test_jobs_for_run.py
tests/report/__init__.py
tests/report/test_view.py
tests/report/test_view_template.py
tests/cli/test_view.py
```

### 5.4 Edits

| File | Change |
|---|---|
| [src/jma/cli.py](../../../src/jma/cli.py) | Remove `TesterHomeSource` import; remove TesterHome branch from `_factory_for`; add `BingAggregatorSource` factory branch; flip `--source` default to `["bing"]`; **drop `--with-detail` flag entirely** (no longer applicable to bing in Phase 2); add new `view` subcommand. CLI fails fast if `SERPAPI_KEY` is unset and `bing` is in the selected sources. |
| [src/jma/sources/base.py](../../../src/jma/sources/base.py) | **Replace** the TesterHome-shaped `SourceConfig` (and its `ListingConfig` / `DetailConfig` sub-models, plus `content_block_markers`, `known_good_list_selector`, `base_url`) with a Bing-shaped `SourceConfig`: `name`, `engine`, `endpoint`, `api_key_env`, `target_sites`, `id_patterns`, `site_names`, `query_template`, `region_aliases`, `rate`. No discriminated union yet — YAGNI until a second source ships. |
| [src/jma/storage/blobs.py](../../../src/jma/storage/blobs.py) | Add optional `suffix: str = ".html.gz"` parameter to `write()`. The bing source passes `suffix=".json.gz"` for SerpAPI page blobs; existing callers (none after TesterHome deletion) keep the default. |
| [src/jma/storage/db.py](../../../src/jma/storage/db.py) | Add `run_jobs.raw_payload_ref TEXT NOT NULL` to the `_DDL` block. Update `insert_jobs` so each `(run_id, job_id)` row written to `run_jobs` carries the blob ref from the `Job` being inserted (alongside the existing `jobs` upsert which keeps latest-seen on the `jobs` row). Add `latest_finished_run(conn) -> Run \| None` and `jobs_for_run(conn, run_id) -> list[Job]` — the latter joins `run_jobs` and hydrates `Job.raw_payload_ref` from `run_jobs.raw_payload_ref` (not from the `jobs` row), so the view sees the snapshot from that specific Run. Domain models return; SQL stays internal. |
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
- Asserts `source == "bing:<host>"` derivation from `link`, with `<host>` matched against `target_sites` (so `www.zhipin.com` and `m.zhipin.com` both collapse to `bing:zhipin.com`).
- Asserts off-target results (host not in `target_sites`) are dropped, with the drop count surfaced in `SourceResult.reason`.
- Asserts `source_internal_id` extracted via per-host URL regex when `id_patterns` matches, falls back to `None` (and `Job.id` falls through to the content-hash branch via `dedup.py:job_id()`).
- Asserts `data_quality == 0.4` for every row.
- Asserts `Location.city is None` and `Location.district is None` for every row.
- Asserts `description_text == result["snippet"]` for every row.
- Asserts the per-page raw blob is written once with `.json.gz` suffix, and the N rows from that page share the same `raw_payload_ref`.
- Asserts region + keyword filtering applies post-fetch the same way as TesterHome.
- **Two `region_aliases` cases parametrised**: `--region Hangzhou` (alias hit, query gets `(Hangzhou OR 杭州 OR 杭州市)`) and `--region Shanghai` (alias miss, identity fallback gets `(Shanghai)` plus an INFO log line). Includes `--region ""` → no region clause in the rendered query.

**`tests/sources/test_bing_company_heuristic.py`** — parameterised over `(title, site_name_for_row, expected_company)`:
- `("AI Agent 工程师 - 阿里巴巴 - BOSS直聘", "BOSS直聘", "阿里巴巴")` — 3-part: middle wins regardless of tail.
- `("AI Engineer | NetEase", "BOSS直聘", "NetEase")` — 2-part, segment_2 ≠ site_name → company.
- `("AI Agent | 拉勾招聘", "拉勾招聘", None)` — 2-part, segment_2 == site_name → drop (locks in the site-name anchor; without this rule the row would silently get `company="拉勾招聘"`).
- `("AI Agent 后端", "BOSS直聘", None)` — 1-part: no delimiter, no signal.
- `("AI Agent | NetEase", None, "NetEase")` — host with no `site_names` entry (e.g. a hypothetical sixth target with no Chinese name): the heuristic still falls through to "treat segment_2 as company" because site_name is `None`, which is correct for English-only board scenarios.

**`tests/live/test_bing_live.py`** — opt-in `@pytest.mark.live`:
- One real SerpAPI call with the full multi-host query template (Hangzhou + "AI agent").
- Asserts ≥1 result whose `link` host matches each `target_sites` entry actually present in the response (validates the `site:` operator works through SerpAPI).
- Asserts ≥1 row across the full response has `salary.parsed=True` AND ≥1 row has `posted_at` set AND ≥1 row has `experience.min_years` set. This is the snippet-richness sanity check: if SerpAPI's snippet content has degraded to title-only across the board, Phase 2's value proposition is gone and we want a red test telling us, not a quiet ship.

**`tests/storage/test_jobs_for_run.py`** — locks in §2 row 17:
- Insert Job X via Run A with `raw_payload_ref="blob_a.json.gz"`. Then insert Job X again (same `id`) via Run B with `raw_payload_ref="blob_b.json.gz"`. The `jobs.raw_payload_ref` upsert advances to `blob_b`.
- Assert `jobs_for_run(A)` returns Job X with `raw_payload_ref == "blob_a.json.gz"` (the snapshot from Run A's observation).
- Assert `jobs_for_run(B)` returns Job X with `raw_payload_ref == "blob_b.json.gz"`.
- Assert the ordering clause: insert 3 jobs with `posted_at = [None, "2026-05-22", "2026-05-23"]` and `fetched_at = [t, t+1, t+2]`. `jobs_for_run` returns them in order `[2026-05-23, 2026-05-22, None]` (posted DESC, NULLS LAST, with fetched DESC tiebreaker exercised on a second NULL-posted row at the tail).

**`tests/report/test_view.py`** — pure:
- Fixture `Run` + 3 fixture `Job`s + fixture `data_root_abs=Path("/tmp/jma-test")` → expected context dict (columns, value formatting like `data_quality=0.4`, em-dash for empty cells, truncated titles, `data_root_abs` propagated to context unmodified). The fixture jobs are pre-ordered (the SQL-side sort is exercised in `test_jobs_for_run.py`, not here).

**`tests/report/test_view_template.py`** — render template against context:
- Asserts via `selectolax` (already a dep): correct number of `<tr>` rows, sortable-by class on `<th>`s, `<a href>` on url + blob cells, run-id prefix in `<h1>`, no `<script src=...>` (offline guarantee).
- Asserts blob `<a href>` starts with `file:///tmp/jma-test/` (absolute `file://` URI rendering from Q8, with `data_root_abs` from context) — and changes to e.g. `file:///opt/data/` when the fixture's `data_root_abs` changes, locking in that the template doesn't hardcode a path.

**`tests/cli/test_view.py`** — Typer `CliRunner`:
- Empty DB → exit code non-zero + `no finished runs in <db_path>` message.
- DB with one finished run → file at `data/view.html` exists, contains run-id prefix, contains "n=<count>".
- `--run <unknown_id>` → exit code non-zero + clear message.

**Test data:**
- `tests/fixtures/serpapi_bing_hangzhou_ai_agent.json` — **captured from one real SerpAPI call during dev** (burns 1 quota credit; cheap and keeps the fixture close to the real schema). Sanitize before commit: strip the API key from the response's `search_parameters.api_key` if present, and confirm the URL set looks generic (no obviously-personal queries). Hand-trim to ≥3 hosts and ≥30 results, with ≥1 row per host that has a parseable salary in its snippet — so unit tests can assert end-to-end snippet → structured-column mapping without a network call. Hand-synthesizing the JSON from SerpAPI's documented schema was the alternative; rejected because the schema can drift quietly between SerpAPI releases and a synthetic fixture wouldn't catch the drift.

## 7. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| SerpAPI's `site:` operator behavior differs from native Bing SERPs | Medium | Live test (`tests/live/test_bing_live.py`) asserts host match. Run once during dev; opt-in marker keeps CI off the network. |
| Snippet quality varies wildly per board (zhipin short, liepin richer); a future SerpAPI/Bing change could degrade snippets to title-only across the board | Medium | Snippet *is* the data in Phase 2 — there is no detail-fetch fallback. `data_quality=0.4` already discounts these in aggregations. The live test (§6 `tests/live/test_bing_live.py`) asserts ≥1 row with parsed salary AND ≥1 with `posted_at` AND ≥1 with experience across the whole response — a tripwire that fires loudly if snippets ever degrade to title-only. |
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
| §4 Phase 2 heading + body | Replace the Randstad/Bing/Playwright narrative with the three-part Phase 2: (a) retire TesterHome, (b) add Bing-aggregator via SerpAPI (snippet-only), (c) add `jma view`. Keep case 2.A (Bing query construction) — still applicable. Drop case 2.B (Randstad variants) — deferred. **Add a new Phase 2.1 heading**: "Detail-fetch enrichment for Bing — deferred. Trigger to re-open: live evidence that at least one target board's detail pages return useful 200s (i.e. anti-bot is not uniform). Cost when revived: extra HTTP budget per crawl, an `--with-detail` flag, the detail outcome matrix from the original spec draft, and a follow-up ADR clause on no-halt-on-detail-block." |
| §5 Risks | Add: "SerpAPI rate-limit (100/mo free) — mitigation: tight default `max_pages`; cache SERP responses for 24h." Add: "PLAN intent of cross-board breadth depends on SerpAPI's `site:` operator behavior on each board — verify against fixture before shipping." Add: "Snippet quality is now the floor of Phase 2 data quality — if a future SerpAPI/Bing change degrades snippet content to title-only, Phase 2 silently drops to title+url+date rows. The live test asserts salary/experience/date richness as a tripwire." |
| §6 Open items | Move Randstad / Playwright / direct-BOSS from Phase 2 to "deferred to a later phase or v1.1 if justified". Add Phase 2.1 (detail-fetch enrichment) under the same heading. |

## 10. New ADR

**`docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md`** — captures:

- The `bing:<host>` source-naming convention (already implied by CONTEXT.md but never formally decided), **including the rule that `<host>` is the matched `target_sites` entry, not the raw URL `netloc`** — so subdomains (`www`, `m`, `app`) collapse and `source` stays a closed vocabulary derived from the YAML.
- The per-host-URL-regex / no-per-host-snippet-regex asymmetry: URL paths are stable vendor convention and change rarely (cheap to maintain a `id_patterns` map in YAML); snippet formats are noisy and Phase 3's LLM extraction will replace any per-site snippet regex, so paying that tax now would be premature.
- **Snippet-only is the only mode in Phase 2**: `data_quality=0.4` for every Bing row, raw snippet stored in `description_text` as Phase 3 LLM-extraction input, and `Location.city=None` because the SERP snippet doesn't reliably disclose workplace (per [CONTEXT.md "Location"](../../../CONTEXT.md#location)).
- The decision to **defer detail-fetch enrichment to Phase 2.1**, with the trigger condition documented (live evidence that ≥1 target board's detail pages aren't anti-bot-walled). When that ADR-0005 amendment lands, the "no-halt-on-detail-block" rule — losing one JD fetch is one row's data-quality drop, not a crawl-ender, because the SerpAPI page is already in hand — becomes the defining departure from TesterHome's `_enrich_page` semantics. Recording the deferred shape here so a future implementer doesn't have to re-derive it from spec history.
- The decision to use SerpAPI as the SERP provider given Bing v7's retirement, and what triggers reconsideration (cost, blocked, alternative emerges).
- A note that this phase introduces the first concrete instance of [ADR-0003](../../adr/0003-url-freshness-as-durable-signal.md)'s flagged "merge by confidence" pattern: `raw_payload_ref` is now split between `jobs.raw_payload_ref` (latest-seen, for aggregation-level reads) and `run_jobs.raw_payload_ref` (per-Run snapshot, for `jobs_for_run`). The same split will eventually apply to `company` / `salary` / `description_text` / `posted_at` when a future ADR generalises the rule.

---

*End of spec. Next step on approval: writing-plans skill produces a per-task implementation plan covering the deletions, the bing source, the view command, the doc/diagram refreshes, and the new ADR.*
