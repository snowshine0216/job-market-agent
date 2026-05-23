# job-market-agent

A small async crawler that pulls job listings from configured sources, normalises
them into a frozen domain model, and persists observations to SQLite. The first
shipping source is [TesterHome](https://testerhome.com/jobs).

> **Status:** Phase 0 + Phase 1 of [PLAN.md](PLAN.md) — project bootstrap and
> the TesterHome vertical slice. Multi-source crawling, LLM extraction, and the
> reporting CLIs land in later phases.

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) for dependency + venv management

## Install

```bash
git clone https://github.com/snowshine0216/job-market-agent
cd job-market-agent
uv sync
```

`uv sync` creates `.venv/` and installs everything pinned in `uv.lock`. No
global pip installs needed.

## Basic usage

```bash
uv run jma crawl --region Hangzhou --keywords "AI agent"
```

### Required flags

| Flag | Purpose |
|---|---|
| `--region <text>` | Filter observations by `Location.city` (NFKC + case-insensitive substring; empty city values are kept so unparseable locations aren't punished). |
| `--keywords <text>` | A single literal phrase matched as NFKC + case-insensitive substring against the raw job title. Repeatable — pass multiple `--keywords` to OR them. `--keywords "AI agent"` matches `"ai agent"` as a phrase, not the union of `"ai"` and `"agent"`. |

### Optional flags

| Flag | Default | Purpose |
|---|---|---|
| `--source <name>` | `testerhome` | Which registered source to crawl. Repeatable. Phase 1 ships only TesterHome. |
| `--max-pages <int>` | `5` | Stop after this many listing pages. |
| `--max-jobs <int>` | `300` | Stop after this many observations are collected (truncated to exactly N). |
| `--no-cache` | off | Skip the 24h URL cache for fetches. Cache rows are still written. |
| `--with-detail` / `--no-detail` | off | Fetch each job's detail page to populate `company`/`salary` and tag URL freshness (`url_status`). Adds N HTTP calls per listing page; respects `delay_ms`. Default off — listing-only crawls do not check URLs. |
| `-v` / `--verbose` | off | Lift log level to `DEBUG`. |

### Example output

```
run_id        : 4f8c2a1b7e9d6c5af0d3e89c1a2b3c4d
region        : Hangzhou
keywords      : AI agent
sources:
  testerhome  : ok    pages=3  jobs=47   elapsed=4.1s
written       : 47 observations to data/jobs.db
```

With `--with-detail`, the summary also reports how many of the just-fetched URLs returned 404/410 (`gone_urls`). Listing-only crawls omit the segment entirely so the operator can distinguish "we didn't check" from "we checked, none gone":

```
testerhome  : ok    pages=3  jobs=47   gone_urls=2   elapsed=12.6s
```

Partial harvest (an earlier page succeeded, a later page was rate-limited):

```
testerhome  : ok    pages=2  jobs=21   elapsed=2.4s  partial: stopped at page 3 (rate_limited: HTTP 429; Retry-After=30s)
```

Hard block (page 1 blocked):

```
testerhome  : blocked  reason="HTTP 403"  pages=1  jobs=0
```

### Exit codes

- `0` — at least one source returned `status=ok` with ≥1 job (includes partial harvests).
- `2` — every source returned non-OK or empty.
- `1` — uncaught exception.

## Where data lands

Everything goes under `data/` (gitignored end-to-end):

```
data/
├── jobs.db                     # SQLite — runs, jobs (observations), run_jobs, url_cache
└── raw/
    └── testerhome/
        └── 20260521/
            └── <sha1>.html.gz  # gzipped raw listing HTML, one file per fetched URL
```

The schema (`runs` + `jobs` + `run_jobs` join + `url_cache`) is bootstrapped
idempotently on every connect — first run creates it, later runs reuse it.

Per-`Job` rows are **observations** keyed by `(source, internal_id)` or a
fallback hash of `(title, company, city)`. A real *Job* is the set of
observations sharing a `canonical_id` (cross-source deduplication —
see [ADR-0001](docs/adr/0001-cross-source-dedup-via-canonical-id.md)).
Aggregations that summarise "jobs" must `GROUP BY canonical_id`.

A Run is one CLI invocation. Membership of an observation in a Run lives in
the `run_jobs` join table — see
[ADR-0002](docs/adr/0002-run-is-one-invocation-recorded-via-join-table.md).

### URL freshness

When run with `--with-detail`, each job's detail page is fetched and the
result is recorded on the `jobs` row as `url_status` (`live` / `gone` /
`unknown`) plus `url_last_checked_at`. Only definitive HTTP outcomes
(200, 404, 410) update these fields; transient outcomes (3xx, 429, 5xx,
network errors) preserve whatever signal was last earned, so a flaky
fetch never erases a previously-confirmed `live` or `gone`. See
[ADR-0003](docs/adr/0003-url-freshness-as-durable-signal.md) and the
[CONTEXT.md URL freshness section](CONTEXT.md#url-freshness) for the
durable-signal model.

### Inspecting the data

The stdout summary shows the headline numbers; for everything else, query
`data/jobs.db` directly. `sqlite3` ships with macOS and most Linux distros.

List recent runs and their per-source outcome:

```bash
sqlite3 -header -column data/jobs.db "
  SELECT id, region, keywords_json, started_at, finished_at
  FROM runs ORDER BY started_at DESC LIMIT 10;"

# Pretty-print the per-source status/reason for the latest run
sqlite3 data/jobs.db "SELECT source_results_json FROM runs
                      ORDER BY started_at DESC LIMIT 1;" | python3 -m json.tool
```

See every observation collected in the most recent run:

```bash
sqlite3 data/jobs.db ".mode line" "
  SELECT j.title, j.company, j.location_city, j.location_work_mode,
         j.salary_raw, j.experience_raw, j.posted_at, j.url, j.raw_payload_ref
  FROM jobs j JOIN run_jobs rj ON rj.job_id = j.id
  WHERE rj.run_id = (SELECT id FROM runs ORDER BY started_at DESC LIMIT 1);"
```

Compact table view across all observations:

```bash
sqlite3 -header -column data/jobs.db "
  SELECT substr(title,1,40) AS title, company, location_city AS city,
         salary_raw AS salary, url
  FROM jobs ORDER BY fetched_at DESC LIMIT 20;"
```

Count unique *Jobs* (deduplicated across observations via `canonical_id` — see
[ADR-0001](docs/adr/0001-cross-source-dedup-via-canonical-id.md); a plain
`COUNT(*)` over `jobs` counts observations, not Jobs):

```bash
sqlite3 data/jobs.db "SELECT COUNT(DISTINCT canonical_id) FROM jobs;"
```

Inspect the raw HTML the parser actually saw — `raw_payload_ref` on each row
points at a gzipped blob under `data/raw/<source>/`:

```bash
sqlite3 data/jobs.db "SELECT raw_payload_ref FROM jobs LIMIT 1;"
gunzip -c data/raw/testerhome/<sha>.html.gz | less
```

Interactive session:

```bash
sqlite3 data/jobs.db
sqlite> .schema jobs        # all 33 columns
sqlite> .mode line          # vertical layout, easier to read
sqlite> SELECT * FROM jobs WHERE location_city = 'Hangzhou' LIMIT 3;
sqlite> .quit
```

Prefer a GUI? Install [DB Browser for SQLite](https://sqlitebrowser.org/)
(`brew install --cask db-browser-for-sqlite` on macOS) and open `data/jobs.db`
— the `runs`, `jobs`, `run_jobs`, and `url_cache` tables are all browsable.

## Configuration

Source selectors and politeness live in checked-in YAML under `config/`:

```
config/sources/testerhome.yaml
```

Selectors, rate (`delay_ms`, `max_retries`, `backoff_base_s`), and content-block
markers are editable per source. The frozen `SourceConfig` pydantic model in
code is the source of truth; the YAML is the user-editable surface.

## Development

```bash
uv run pytest           # full suite, live smoke deselected
uv run pytest -m live   # opt-in TesterHome live smoke (one real fetch)
uv run ruff check .     # lint
```

The default `pytest` invocation skips `@pytest.mark.live` tests via
`addopts = -m "not live"` in `pyproject.toml`, so CI never hits the network.
Live smoke runs only when asked for explicitly.

Layout:

```
src/jma/
├── cli.py                Typer entrypoint
├── domain/               pure functions — models, normalize, blockage, dedup
├── sources/              JobSource Protocol, async HTTP client, TesterHome impl
├── storage/              SQLite, URL cache, gzipped blob writer/reader
└── pipeline/             single-source crawl orchestration
```

`domain/` is pure (no I/O, no clock, no globals). All I/O is isolated to
`sources/http.py`, `storage/*`, `pipeline/crawl.py`, and `cli.py`.

## Documentation

- [PLAN.md](PLAN.md) — overall roadmap and decision table.
- [CONTEXT.md](CONTEXT.md) — glossary (JobObservation vs Job, PartialHarvest, Run, Source).
- [docs/adr/](docs/adr/) — architectural decisions (dedup model, Run semantics, URL freshness durable signal).
- [docs/superpowers/specs/](docs/superpowers/specs/) — implementation specs per phase.
