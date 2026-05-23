# Phase 0 + Phase 1 Design — Foundation + TesterHome Vertical Slice

> Implementation spec for `PLAN.md` Phases 0 and 1.
>
> Date: 2026-05-21 · Status: ready for implementation plan (rev 2,
> incorporates `/grill-with-docs` resolutions)
>
> Parent: [PLAN.md](../../../PLAN.md). PLAN's decision table (rows 1–17)
> is the source of truth for what we are building. This spec resolves
> the implementation-level branches PLAN deferred.
>
> Companion docs:
> [CONTEXT.md](../../../CONTEXT.md) (glossary),
> [ADR-0001](../../adr/0001-cross-source-dedup-via-canonical-id.md)
> (cross-source dedup),
> [ADR-0002](../../adr/0002-run-is-one-invocation-recorded-via-join-table.md)
> (Run + join table).

---

## 1. Scope

**In scope**
- Project bootstrap: `pyproject.toml` via `uv`, `ruff`, `pytest`,
  `pytest-asyncio`, `respx`, `pydantic v2`, `httpx`, `selectolax`, `typer`,
  `aiosqlite`, `pyyaml`.
- Full v1 dataclasses in `domain/models.py` (`Job` + sub-objects,
  `SourceResult`, `MarketReport`, `FitReport`). Pydantic v2 `BaseModel`
  with `model_config = ConfigDict(frozen=True)`. Phase 3+ fills empty
  fields; the model never gains or loses fields after this spec lands.
- `domain/normalize.py` — pure parsers (`parse_salary`, `parse_experience`,
  `parse_location`) backed by PLAN case 1.A corpus.
- `domain/blockage.py` — pure `classify(...) → BlockStatus`, HTTP +
  soft-block detection only.
- `domain/dedup.py` — pure `job_id(...) → str` and
  `canonical_id(...) → str`.
- `sources/base.py` — `JobSource` Protocol + `SourceConfig` loader.
- `sources/http.py` — `httpx.AsyncClient` wrapper with retry/backoff,
  hands responses to the classifier.
- `sources/testerhome.py` — first concrete `JobSource`.
- `config/sources/testerhome.yaml` — selectors + politeness config.
- `storage/db.py` — `aiosqlite` connection, idempotent schema bootstrap,
  `start_run`, `finish_run`, `insert_jobs`.
- `storage/cache.py` — 24h URL cache against `url_cache` table.
- `storage/blobs.py` — gzipped raw HTML at
  `data/raw/{source}/{yyyymmdd}/{sha1(url)[:16]}.html.gz`.
- `pipeline/crawl.py` — single-source orchestration.
- `cli.py` — Typer app exposing `jma crawl …` only.

**Out of scope (deferred)**
- `randstad.py`, `bing.py`, `browser.py` (Phase 2).
- LLM client, extraction, narration (Phase 3+).
- `jma sources status`, `jma report …`, `jma run`, multi-source
  orchestration, `--concurrency` / `--delay-ms` flags (Phase 2+).
- `config/skills.yaml`, `config/region_aliases.yaml` (Phase 3 / 2).

## 2. Decisions resolved by this spec

PLAN.md left eight implementation branches open; the first pass of this
spec resolved them and a `/grill-with-docs` interview resolved ten more.
The table below is the merged current state.

| # | Branch | Decision |
|---|---|---|
| 1 | Future-only Job fields at Phase 0 | Define all v1 fields up-front with safe defaults (`[]`, `""`, `UNKNOWN`, `None`). Phase 3+ fills; schema never alters. |
| 2 | Sync vs async at Phase 1 | Async from day 1. `httpx.AsyncClient`, `pytest-asyncio`, `asyncio.run` in CLI. |
| 3 | SQLite schema scope | `jobs` + `url_cache` + `runs` + `run_jobs`. `runs` + `run_jobs` exist at Phase 1 so Phase 6 cross-run delta is a SQL query, not a migration. |
| 4 | Dedup model | **Cross-source from day 1, via two keys.** Per-`JobObservation` `id = sha1(source ':' internal_id)` when present, fallback `sha1(source ':' normalize(title) '\|' company '\|' city)`. Per-`Job` `canonical_id = sha1(normalize(title) '\|' normalize(company) '\|' normalize(city))`. `jobs` rows are JobObservations; aggregations `GROUP BY canonical_id`. See [ADR-0001](../../adr/0001-cross-source-dedup-via-canonical-id.md). |
| 5 | `source` string format | `<crawler>[':' <origin_site>]`. Direct crawlers: `testerhome`, `randstad`. Aggregator-prefixed: `bing:zhaopin.com`. |
| 6 | Run semantics | A Run is one CLI invocation. `runs.id = UUID4`. `jobs` has no `run_id` column; membership lives in a `run_jobs(run_id, job_id)` join table. See [ADR-0002](../../adr/0002-run-is-one-invocation-recorded-via-join-table.md). |
| 7 | `--region` / `--keywords` semantics | Region filters JobObservations on `Location.city` (empty city kept; non-empty city must equal region, case-insensitive substring). Each `--keywords` is one literal phrase (NFKC + case-insensitive substring on `title_raw`); multiple `--keywords` are OR'd. Alias expansion is Phase 2. |
| 8 | Blockage classifier location & scope | `domain/blockage.py`, signature `classify(status_code, headers, body_text, cfg) → BlockStatus`. Pure, no httpx dependency. **HTTP + soft-block only**: parse-result decisions (zero items, end-of-listing) live in the per-source crawl loop. |
| 9 | PartialHarvest convention | If a later page is blocked but earlier pages succeeded, the source returns `SourceResult(status=OK, jobs=tuple(collected), reason=f"partial: stopped at page N (...)")`. Page-1 hard block still returns the block's status with zero jobs. |
| 10 | Crawl termination | Three rules: `max_pages` cap; `max_jobs` cap (truncate to exactly N); natural end-of-listing (`parsed_count == 0 AND collected > 0`). The "two consecutive empty pages" heuristic from the first pass is dropped. |
| 11 | Salary disclosure model | Three states exposed via `Salary.disclosure` property: `parseable` (parsed=True), `unparseable` (parsed=False, raw non-empty), `absent` (parsed=False, raw=""). `currency = None` for all unparseable salaries (no language inference). `min`/`max` are populated only when `parsed=True AND period in {MONTHLY, ANNUAL}`. |
| 12 | Raw blob path scheme | `data/raw/{source}/{yyyymmdd}/{sha1(url)[:16]}.html.gz`. Date-sharded, deterministic. |
| 13 | Directory layout | `config/` for checked-in ship-with-code config (source YAMLs; Phase 3 adds `skills.yaml`, `region_aliases.yaml`). `data/` for entirely-gitignored runtime state (`jobs.db`, `raw/`). |
| 14 | Testing posture | Unit + offline e2e (respx) in CI; opt-in live smoke via `@pytest.mark.live`, `pytest` defaults to `-m "not live"`. |
| 15 | CLI surface | `jma crawl --region <text> --keywords <text> [--keywords …] [--source testerhome] [--max-pages 5] [--max-jobs 300] [--no-cache] [-v]`. Repeatable `--keywords`. |

## 3. Module layout

```
job-market-agent/
├── pyproject.toml                                ← new
├── ruff.toml                                     ← new (or [tool.ruff] in pyproject)
├── CONTEXT.md                                    ← exists
├── docs/adr/                                     ← exists (0001, 0002)
├── config/
│   └── sources/
│       └── testerhome.yaml                       ← new (checked in)
├── data/                                         ← entirely gitignored
│   ├── .gitignore                                ← `*` ignore-all
│   ├── jobs.db                                   ← runtime
│   └── raw/                                      ← runtime
├── src/jma/
│   ├── __init__.py
│   ├── cli.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── normalize.py
│   │   ├── blockage.py
│   │   └── dedup.py                              ← job_id + canonical_id
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── http.py
│   │   └── testerhome.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── cache.py
│   │   └── blobs.py
│   └── pipeline/
│       ├── __init__.py
│       └── crawl.py
└── tests/
    ├── conftest.py
    ├── fixtures/sources/testerhome/
    │   ├── listing_ok.html
    │   ├── listing_empty.html
    │   └── detail_ok.html                        ← reserved for Phase 3
    ├── domain/
    │   ├── test_models.py
    │   ├── test_normalize_salary.py
    │   ├── test_normalize_experience.py
    │   ├── test_normalize_location.py
    │   ├── test_blockage.py
    │   └── test_dedup.py                         ← job_id + canonical_id
    ├── sources/
    │   ├── test_source_config.py
    │   ├── test_http.py
    │   └── test_testerhome.py                    ← incl. region filter + PartialHarvest
    ├── storage/
    │   ├── test_db.py
    │   ├── test_cache.py
    │   └── test_blobs.py
    ├── pipeline/
    │   └── test_crawl_e2e.py
    ├── cli/
    │   └── test_cli.py
    └── live/
        └── test_testerhome_live.py               ← @pytest.mark.live, off by default
```

## 4. Data models (`src/jma/domain/models.py`)

All models are `pydantic.BaseModel` with
`model_config = ConfigDict(frozen=True)`. Enums are `str`-valued so they
serialise cleanly into SQLite TEXT columns.

```python
class WorkMode(str, Enum):
    ONSITE = "onsite"; REMOTE = "remote"; HYBRID = "hybrid"; UNKNOWN = "unknown"

class Seniority(str, Enum):
    JUNIOR = "junior"; MID = "mid"; SENIOR = "senior"; STAFF = "staff"
    LEAD = "lead"; UNKNOWN = "unknown"

class SalaryPeriod(str, Enum):
    MONTHLY = "monthly"; ANNUAL = "annual"; DAILY = "daily"
    HOURLY = "hourly"; UNKNOWN = "unknown"

class SourceStatus(str, Enum):
    OK = "ok"; EMPTY = "empty"; BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"; ERROR = "error"

class Location(BaseModel):
    country: str | None = None        # ISO-2 ("CN", "US"); None if unknown
    city: str | None = None           # canonical English ("Hangzhou")
    district: str | None = None       # native script OK ("余杭")
    work_mode: WorkMode = WorkMode.UNKNOWN

class Salary(BaseModel):
    min: int | None = None            # monthly equivalent; populated only if parsed AND period ∈ {MONTHLY, ANNUAL}
    max: int | None = None            # same rule as min
    currency: str | None = None       # "CNY", "USD", "HKD"; None for unparseable disclosures (no language inference)
    period: SalaryPeriod = SalaryPeriod.UNKNOWN   # period of the ORIGINAL string
    months_per_year: int | None = None            # 12, 13, 14, 15
    raw: str = ""
    parsed: bool = False              # True ⇒ min/max + currency populated (for MONTHLY/ANNUAL)

    @property
    def disclosure(self) -> Literal["parseable", "unparseable", "absent"]:
        if self.parsed:
            return "parseable"
        return "absent" if self.raw == "" else "unparseable"

class Experience(BaseModel):
    min_years: int | None = None
    max_years: int | None = None
    raw: str = ""

class BlockStatus(BaseModel):
    kind: SourceStatus
    reason: str = ""
    evidence: str = ""                # ≤200 chars, optional

class Job(BaseModel):
    id: str                           # JobObservation id; see dedup.job_id()
    canonical_id: str                 # Job id; see dedup.canonical_id() — non-unique, groups cross-source observations
    source: str                       # "testerhome" (direct), "bing:zhaopin.com" (aggregator). See PLAN row 2 and CONTEXT.md "Source".
    source_internal_id: str | None = None
    title: str
    title_raw: str
    company: str | None = None
    location: Location
    salary: Salary
    experience: Experience
    skills_raw: list[str] = []        # Phase 3 fills
    skills_canonical: list[str] = []  # Phase 3 fills
    seniority: Seniority = Seniority.UNKNOWN  # Phase 3 fills
    responsibilities_summary: str = ""        # Phase 3 fills
    description_text: str = ""        # Phase 1 leaves empty; Phase 3 fills from detail page
    posted_at: datetime | None = None
    fetched_at: datetime
    url: str
    raw_payload_ref: str              # "raw/testerhome/20260521/abc123…html.gz"
    data_quality: float = 1.0         # Phase 2 lowers for snippet-only

class SourceResult(BaseModel):
    source: str
    status: SourceStatus
    jobs: tuple[Job, ...] = ()        # tuple, not list, to keep model hashable
    reason: str = ""                  # carries PartialHarvest detail when status=OK and reason starts with "partial:"
    pages_fetched: int = 0
    elapsed_ms: int = 0

class MarketReport(BaseModel):        # Phase 4 fills
    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    stats_json: dict[str, object] = {}
    narrative_md: str = ""

class FitReport(BaseModel):           # Phase 5 fills
    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    profile_id: str = ""
    top_jobs_md: str = ""
    synthesis_md: str = ""
```

**Contracts:**
- `Salary.disclosure` is the three-way enum aggregators read. Phase 4's
  monthly-salary aggregations consume only `disclosure == "parseable"
  AND period in {MONTHLY, ANNUAL}` rows. PLAN risk row 3 (`面议 /
  Competitive`) is the `"unparseable"` case.
- Frozen models: parsers return new instances; no in-place mutation.
- `Job.id` identifies a [JobObservation](../../../CONTEXT.md). A real
  [Job](../../../CONTEXT.md) is the set of JobObservations sharing a
  `canonical_id`. Aggregations that summarise "jobs" must
  `GROUP BY canonical_id` and pick the highest-`data_quality` row per
  group; forgetting this double-counts.
- `SourceResult(status=OK, reason=startswith("partial:"))` signals a
  [PartialHarvest](../../../CONTEXT.md). The CLI exit-code rule and
  Phase-4 freshness footnotes both branch on this.

## 5. SQLite schema

`storage/db.py` bootstraps this DDL on every connect — `CREATE … IF NOT
EXISTS` makes the call idempotent.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id                  TEXT PRIMARY KEY,        -- UUID4 (no derived hash)
    region              TEXT NOT NULL,
    keywords_json       TEXT NOT NULL,           -- JSON array
    started_at          TEXT NOT NULL,           -- ISO-8601 UTC
    finished_at         TEXT,                    -- NULL until run completes
    source_results_json TEXT                     -- list[SourceResult] (sans .jobs) on finish
);

CREATE INDEX IF NOT EXISTS idx_runs_region_started ON runs(region, started_at);

CREATE TABLE IF NOT EXISTS jobs (
    id                       TEXT PRIMARY KEY,   -- JobObservation id; sha1(source ':' internal_id) or fallback
    canonical_id             TEXT NOT NULL,      -- Job id; sha1(normalize(title) '|' company '|' city). Non-unique index.
    source                   TEXT NOT NULL,
    source_internal_id       TEXT,
    title                    TEXT NOT NULL,
    title_raw                TEXT NOT NULL,
    company                  TEXT,
    location_country         TEXT,
    location_city            TEXT,
    location_district        TEXT,
    location_work_mode       TEXT NOT NULL,
    salary_min               INTEGER,
    salary_max               INTEGER,
    salary_currency          TEXT,
    salary_period            TEXT NOT NULL,
    salary_months_per_year   INTEGER,
    salary_raw               TEXT NOT NULL DEFAULT '',
    salary_parsed            INTEGER NOT NULL,   -- 0/1
    experience_min_years     INTEGER,
    experience_max_years     INTEGER,
    experience_raw           TEXT NOT NULL DEFAULT '',
    skills_raw_json          TEXT NOT NULL DEFAULT '[]',
    skills_canonical_json    TEXT NOT NULL DEFAULT '[]',
    seniority                TEXT NOT NULL,
    responsibilities_summary TEXT NOT NULL DEFAULT '',
    description_text         TEXT NOT NULL DEFAULT '',
    posted_at                TEXT,
    fetched_at               TEXT NOT NULL,
    url                      TEXT NOT NULL,
    raw_payload_ref          TEXT NOT NULL,
    data_quality             REAL NOT NULL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_jobs_canonical   ON jobs(canonical_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source      ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched_at  ON jobs(fetched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_city        ON jobs(location_city);

CREATE TABLE IF NOT EXISTS run_jobs (
    run_id    TEXT NOT NULL REFERENCES runs(id),
    job_id    TEXT NOT NULL REFERENCES jobs(id),
    PRIMARY KEY (run_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_run_jobs_job ON run_jobs(job_id);

CREATE TABLE IF NOT EXISTS url_cache (
    url_sha1     TEXT PRIMARY KEY,               -- sha1(canonical_url)
    url          TEXT NOT NULL,
    source       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,                  -- ISO-8601 UTC
    status_code  INTEGER NOT NULL,
    blob_ref     TEXT                            -- NULL if fetch failed
);

CREATE INDEX IF NOT EXISTS idx_url_cache_fetched ON url_cache(fetched_at);
```

- **Run-id:** `uuid.uuid4().hex`. Every `jma crawl` invocation is a new
  Run regardless of inputs; same-day re-runs are distinct rows.
- **Cache TTL:** a URL is fresh iff `now - fetched_at < 24h` AND
  `status_code == 200`. Otherwise re-fetch.
- **Insert flow per page:**
  - `INSERT OR REPLACE INTO jobs (...)` — latest observation wins for
    per-source fields.
  - `INSERT OR IGNORE INTO run_jobs (run_id, job_id) VALUES (?, ?)` —
    every Run that observed a JobObservation gets a permanent edge.
- **Aggregation discipline:** every query that summarises "jobs" rather
  than "observations" must `GROUP BY canonical_id` and pick a
  representative row (highest `data_quality`, ties broken by
  `fetched_at DESC`). Helpers in `domain/stats.py` will encapsulate
  this in Phase 4 — Phase 1's `pipeline.crawl` does not aggregate.

## 6. Blockage classifier (`src/jma/domain/blockage.py`)

```python
# This classifier handles HTTP + soft-block detection only.
# Parse-result-based decisions (zero items, partial harvest,
# end-of-listing) live in the per-source crawl loop (see §7.3).
def classify(
    status_code: int,
    headers: Mapping[str, str],
    body_text: str,
    cfg: SourceConfig,
) -> BlockStatus: ...
```

`SourceConfig` exposes `content_block_markers: tuple[str, ...]`. The
`known_good_list_selector` lives on `SourceConfig` for the crawl loop
to reference; the classifier no longer needs it.

**Decision tree — first match wins:**

| # | Condition | Output |
|---|---|---|
| 1 | `status_code == 429` | `BlockStatus(RATE_LIMITED, reason=f"HTTP 429; Retry-After={headers.get('retry-after','?')}s")` |
| 2 | `status_code in {401, 403}` | `BlockStatus(BLOCKED, reason=f"HTTP {status_code}")` |
| 3 | `status_code >= 500` | `BlockStatus(ERROR, reason=f"HTTP {status_code}")` |
| 4 | `status_code != 200` (any other non-OK) | `BlockStatus(ERROR, reason=f"HTTP {status_code}")` |
| 5 | any `marker in body_text` for marker in `cfg.content_block_markers` | `BlockStatus(BLOCKED, reason=f"soft-block: {marker}", evidence=snippet_around(body_text, marker, 120))` |
| 6 | `body_text == ""` | `BlockStatus(ERROR, reason="empty response body")` |
| 7 | otherwise | `BlockStatus(OK)` |

**Properties:** pure (no I/O, no globals, no clock); `evidence` capped
at ≤200 chars; markers list configurable per source (TesterHome ships
`[]`). Cases that depended on `parsed_count` in the first pass now live
in §7.3.

`snippet_around(text, marker, radius)` returns `text[max(0,
i-radius):i+len(marker)+radius]` where `i = text.find(marker)`, then
collapses any run of whitespace to a single space. Pure helper inside
`domain/blockage.py`.

## 7. TesterHome source

### 7.1 Config — `config/sources/testerhome.yaml`

```yaml
name: testerhome
base_url: https://testerhome.com
listing:
  url_template: "{base_url}/jobs?page={page}"
  list_item_selector: ".topics .topic"
  title_selector: ".title a"
  href_attr: "href"
  posted_at_attr: ".time@title"
detail:
  body_selector: ".topic-detail .markdown-body"
requires_browser: false
content_block_markers: []
known_good_list_selector: ".topics .topic"
rate:
  delay_ms: 800
  max_retries: 3
  backoff_base_s: 2
```

A frozen `SourceConfig` pydantic model is the in-code source of truth;
the YAML is the user-editable surface.

### 7.2 `JobSource` Protocol — `sources/base.py`

```python
class JobSource(Protocol):
    name: str
    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult: ...
```

### 7.3 `TesterHomeSource` algorithm

Per-page loop, building up `collected: list[Job]`:

1. Render `listing.url_template` with `page=n`.
2. `storage.cache.get(url)`: on hit-fresh, reuse cached blob path + read
   body from disk (treat as `status_code=200, headers={}` for the
   classifier). On miss/stale, `http.fetch(url)` and write fresh blob +
   cache row.
3. `block = classify(status_code, headers, body_text, cfg)`. If
   `block.kind != OK`:
   - If `collected`: return
     `SourceResult(status=OK, jobs=tuple(collected), reason=f"partial: stopped at page {n} ({block.kind.value}: {block.reason})", pages_fetched=n)`.
     This is a [PartialHarvest](../../../CONTEXT.md).
   - Else: return `SourceResult(status=block.kind, jobs=(), reason=block.reason, pages_fetched=n)`.
4. Parse with `selectolax`: collect `(title_text, href,
   posted_at_attr_value)` for each `list_item_selector` match. Set
   `parsed_count = len(items)`.
5. **End-of-listing check.** If `parsed_count == 0`:
   - If `collected`: return
     `SourceResult(status=OK, jobs=tuple(collected), reason=f"end of listing at page {n}", pages_fetched=n)`.
   - Else: return
     `SourceResult(status=EMPTY, jobs=(), reason=f"0 items at {cfg.known_good_list_selector!r} on page 1", pages_fetched=n)`.
6. For each item, build a listing-only `Job`:
   - `title_raw` = anchor text.
   - `title` = `title_raw` with salary tokens stripped (regex covering
     `\d+-\d+[Kk万]·\d+薪`, `\d+-\d+[Kk]`, `年薪 \d+-\d+万`,
     `\$\d+K[-–]\$?\d+K`).
   - `salary` = `parse_salary(extracted_token_or_empty)`.
   - `location` = `parse_location(title_raw)`; TesterHome prefixes city
     in `【杭州·余杭】` form.
   - `experience` = `parse_experience(title_raw)`.
   - `source_internal_id` = topic id from `href` via regex
     `/topics/(\d+)`.
   - `url` = `urljoin(base_url, href)`.
   - `posted_at` = `datetime.fromisoformat(posted_at_attr)` or `None`.
   - `id` = `domain.dedup.job_id(source="testerhome",
     internal_id=topic_id, title=title, company=company,
     city=location.city)`.
   - `canonical_id` = `domain.dedup.canonical_id(title=title,
     company=company, city=location.city)`.
   - `raw_payload_ref` = the listing-page blob ref (all jobs on a page
     share it).
   - `fetched_at` = `datetime.now(timezone.utc)`.
   - `data_quality` = `1.0`.
   - `description_text` = `""`.
7. **Region filter.** Drop items where `location.city` is non-empty and
   does not equal `region` (NFKC + case-insensitive substring;
   `region` matches any city containing it as a substring, so
   `--region Hangzhou` matches `Hangzhou` and `Greater Hangzhou`).
   Items with `location.city == None` are kept (we don't punish
   unparseable locations).
8. **Keyword filter.** Keep items whose `title_raw` contains *any*
   `--keywords` phrase (NFKC + case-insensitive substring). Each
   `--keywords` argument is one literal phrase — `--keywords "AI agent"`
   matches the substring `"ai agent"`, not the individual tokens.
9. Append the post-filter items to `collected`.
10. **`max_jobs` check.** If `len(collected) >= max_jobs`: truncate
    `collected` to exactly `max_jobs` and return
    `SourceResult(status=OK, jobs=tuple(collected), reason="max_jobs reached", pages_fetched=n)`.
11. **`max_pages` check.** If `n == max_pages`: return
    `SourceResult(status=OK, jobs=tuple(collected), reason="max_pages reached", pages_fetched=n)`.
12. Sleep `cfg.rate.delay_ms`, advance to `n+1`.

When the loop exits naturally on max_pages, the SourceResult carries
the full `collected` set with `status=OK`.

**Phase 1 does not fetch detail pages.** PLAN case 1.C: the listing
already carries title + salary, enough for the Phase-1 vertical slice.
Detail fetch enters in Phase 3 when LLM extraction needs JD bodies.

## 8. CLI (`src/jma/cli.py`)

```
jma crawl --region <text> --keywords <text> [--keywords <text> …]
          [--source testerhome]
          [--max-pages 5]
          [--max-jobs 300]
          [--no-cache]
          [-v | --verbose]
```

- `--region` (required, single string): filters JobObservations on
  `Location.city` (empty city = keep); stamped on the `runs` row.
- `--keywords` (required, repeatable): OR-set of literal phrases.
  Matches `title_raw` as NFKC + case-insensitive substring. **Each
  `--keywords` is a phrase, not a tokenised query** —
  `--keywords "AI agent"` matches `"ai agent"`, not the union of
  `"ai"` and `"agent"`.
- `--source` (optional, repeatable; default = all registered sources).
- `--max-pages` (default 5), `--max-jobs` (default 300): caps; first
  hit wins. `--max-jobs` truncates to exactly N rather than overshooting.
- `--no-cache`: skip the 24h URL cache for fetches; still writes cache
  rows (`INSERT OR REPLACE`). Non-200 rows are never "fresh", so the
  cache is self-healing on the next normal run.
- `-v`: lift log level to DEBUG (INFO default; stdlib `logging`).

**Exit codes:** 0 if any source returned `status=OK` with ≥1 job (which
includes PartialHarvests); 2 if every source returned non-OK or
empty-OK; 1 on uncaught exception.

**Stdout summary on success:**

```
run_id        : 4f8c2a1b7e9d6c5af0d3e89c1a2b3c4d
region        : Hangzhou
keywords      : AI agent
sources:
  testerhome  : ok    pages=3  jobs=47   elapsed=4.1s
written       : 47 observations to data/jobs.db
```

PartialHarvest line:
`testerhome  : ok    pages=2  jobs=21   elapsed=2.4s  partial: stopped at page 3 (rate_limited: HTTP 429; Retry-After=30s)`.

Non-OK source line: `testerhome  : blocked  reason="HTTP 403"  pages=1
jobs=0`. The CLI never silently swallows a non-OK source.

`cli.py` wires `httpx.AsyncClient`, the source registry, the
`aiosqlite` connection, calls `pipeline.crawl.run(...)`, and runs the
async flow under a single `asyncio.run(...)` at the top of the Typer
command.

## 9. Testing strategy

| Layer | Files | What it covers | Network |
|---|---|---|---|
| Pure-function unit | `tests/domain/test_normalize_*.py`, `test_blockage.py`, `test_dedup.py`, `test_models.py` | PLAN 1.A salary corpus (8 rows) + 4 added rows for whitespace/NFKC; experience + location parsers; classifier (5 HTTP/marker cases + 2 properties); dedup: `job_id` determinism + source-scoping + NFKC/whitespace collapse; `canonical_id` determinism + source-independence; frozen-model defaults; `Salary.disclosure` three-way property | none |
| Source unit | `tests/sources/test_source_config.py`, `test_http.py`, `test_testerhome.py` | YAML round-trip + missing-key error; http retry/backoff via `respx` against 200/429/403/5xx; TesterHome parser against `listing_ok.html` (≥20 items), region filter behaviour, keyword filter behaviour (literal phrase semantics), end-of-listing on `listing_empty.html` (status=EMPTY on page 1, status=OK + "end of listing" reason on page N>1), PartialHarvest on respx-injected 429 at page 2 | `respx` |
| Storage unit | `tests/storage/test_db.py`, `test_cache.py`, `test_blobs.py` | idempotent schema bootstrap, `INSERT OR REPLACE` on duplicate id, `INSERT OR IGNORE` on `run_jobs`, `GROUP BY canonical_id` round-trip on synthetic two-source dataset, cache TTL boundary at 23h59m / 24h01m, blob path scheme + gzip round-trip | tmp dirs only |
| Offline e2e | `tests/pipeline/test_crawl_e2e.py` | full `pipeline.crawl.run(...)` against `respx`-mocked TesterHome pages 1–3 + fixture HTML; asserts `runs` row, ≥1 `jobs` row with non-empty `canonical_id`, matching `run_jobs` edges, blob file present, URL cache populated | `respx` only |
| CLI | `tests/cli/test_cli.py` | `typer.testing.CliRunner`: stdout summary snapshot, exit code 0 on success and on PartialHarvest with jobs, exit code 2 on all-blocked / all-empty | none |
| Live smoke | `tests/live/test_testerhome_live.py` (`@pytest.mark.live`) | one real fetch of `https://testerhome.com/jobs?page=1`; asserts `SourceResult.status == OK` and `len(jobs) >= 1`; skipped by default, run via `pytest -m live` | yes |

`pyproject.toml` registers the `live` marker and configures `pytest`
defaults to **`-m "not live"`**.

## 10. Phase 1 exit criteria

1. All non-live tests green (`pytest`).
2. `pytest -m live` green on the maintainer's machine. Run manually
   before declaring the phase done; failure does not block CI but does
   block phase completion.
3. Manual command works:
   ```
   $ jma crawl --region Hangzhou --keywords "AI agent"
   ```
   produces ≥1 row in `data/jobs.db` (with non-empty `canonical_id`), a
   matching `run_jobs` edge, a corresponding gzipped blob under
   `data/raw/testerhome/<yyyymmdd>/`, and a `runs` row whose
   `source_results_json` reports `status == ok`.
4. `ruff check` clean.

## 11. Implementation order (TDD slices)

Each slice writes the failing tests first, then the minimum code to
turn them green, then a refactor pass. Each slice is shippable on its
own.

| # | Slice | Red tests |
|---|---|---|
| 0.1 | `pyproject.toml`, ruff + pytest config, `config/` + `data/` layout with `.gitignore`s | smoke: `pytest` exits 0 |
| 0.2 | `domain/models.py` — all dataclasses + enums frozen, `Salary.disclosure` property | `test_models.py`: frozen behaviour, defaults, `Salary.disclosure` three-way, Job round-trip via `model_dump` / `model_validate` |
| 1.1 | `domain/normalize.py::parse_salary` | `test_normalize_salary.py` (PLAN 1.A + 4 added rows; `currency=None` for unparseable; `min/max=None` for DAILY/HOURLY) |
| 1.2 | `domain/normalize.py::parse_experience`, `parse_location` | `test_normalize_experience.py`, `test_normalize_location.py` |
| 1.3 | `domain/dedup.py::job_id` + `canonical_id` | `test_dedup.py`: `job_id` determinism, source-scoping, NFKC/whitespace collapse; `canonical_id` determinism, source-independence, identical for same (title, company, city) regardless of source |
| 1.4 | `domain/blockage.py::classify` + `BlockStatus` | `test_blockage.py`: 5 HTTP/marker cases + 2 properties (pure, evidence ≤200 chars) |
| 1.5 | `sources/base.py` Protocol + `SourceConfig` loader | `test_source_config.py`: YAML round-trip, missing-key error |
| 1.6 | `sources/http.py` `AsyncHttpClient` (retry + backoff, calls classify) | `test_http.py`: `respx` 200/429/403/5xx, asserts retry count + final outcome |
| 1.7 | `storage/db.py` — schema bootstrap (incl. `run_jobs`), `start_run`, `finish_run`, `insert_jobs` (`INSERT OR REPLACE` on `jobs`, `INSERT OR IGNORE` on `run_jobs`) | `test_db.py`: idempotent bootstrap, insert/replace, `GROUP BY canonical_id` round-trip on synthetic two-source dataset |
| 1.8 | `storage/cache.py` — `get`/`put` w/ 24h TTL | `test_cache.py`: TTL boundary |
| 1.9 | `storage/blobs.py` — `write(source, url, body) → ref`, `read(ref) → str` | `test_blobs.py`: path scheme, gzip round-trip |
| 1.10 | `sources/testerhome.py` | `test_testerhome.py`: against `listing_ok.html` and `listing_empty.html`; region filter; keyword phrase semantics; PartialHarvest at page 2; end-of-listing at page N>1 |
| 1.11 | `pipeline/crawl.py::run(region, keywords, sources, caps, no_cache)` | `test_crawl_e2e.py`: respx-mocked end-to-end including `run_jobs` edges |
| 1.12 | `cli.py jma crawl` | `test_cli.py` via `CliRunner`: success summary, PartialHarvest summary, all-blocked exit code 2 |
| 1.13 | Live smoke + manual smoke per §10 | `tests/live/test_testerhome_live.py` |

Slices 0.1–0.2 are PLAN's Phase 0 (~½ day). Slices 1.1–1.13 are
PLAN's Phase 1 (~2–3 days).

## 12. Risks & mitigations specific to this spec

| Risk | Mitigation |
|---|---|
| Aggregation forgets to `GROUP BY canonical_id`, double-counts JobObservations | `domain/stats.py` (Phase 4) encapsulates the grouping; Phase 1's `test_db.py` includes a synthetic two-source dataset that proves the grouping query returns one row per canonical Job; CONTEXT.md and ADR-0001 codify the discipline. |
| TesterHome DOM changes break the parser | Captured HTML fixtures in `tests/fixtures/sources/testerhome/`; live smoke (`-m live`) catches drift manually before each phase exit; selectors live in YAML so a fix is one file change. |
| `parse_salary` corpus too small to be load-bearing | PLAN 1.A is the seed; +4 added rows for whitespace/NFKC/Unicode-digit cases; `unparseable → Salary(parsed=False, raw=raw)` is the safe default, never a raise. |
| Async-from-day-one over-engineers Phase 1 | All async surface is single-task in Phase 1 (one source, one page at a time). The shape is identical to the sync version aside from `async def` / `await`. The setup cost (pytest-asyncio, `asyncio.run`) is paid once. |
| SQLite write contention from concurrent runs | WAL journal mode + the fact that Phase 1 has a single writer per `jma crawl` invocation. Concurrent crawls are not supported in Phase 1; Phase 2 revisits if needed. |
| PartialHarvest reason buried in `SourceResult.reason` string is missed by callers | CLI explicitly checks `reason.startswith("partial:")` and prints a dedicated line; Phase 4 reports footnote the share of PartialHarvest sources; convention codified in CONTEXT.md. |
| Live test gets the project blocked from TesterHome | Live test runs only on `-m live`, not in CI; one request per run; `delay_ms 800` applies. |

---

*End of spec. Next step on approval: writing-plans skill produces the
implementation plan from this document.*
