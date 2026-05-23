# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`jma` — a Python 3.12 CLI that crawls job postings, persists them to SQLite + gzipped raw HTML blobs, and (later phases) produces market-overview and personal-fit reports. Phase 1 ships only the TesterHome crawler vertical slice; multi-source, LLM extraction, and reports come in later phases. See [PLAN.md](PLAN.md) for the full phase plan and locked decisions.

## Tooling — uv

This project uses **uv**, not pip/venv/poetry. Always invoke Python through uv so the lockfile (`uv.lock`) and `.venv/` stay consistent.

```bash
uv sync                                  # install deps + dev group from uv.lock
uv run jma --help                        # run the CLI entrypoint (project.scripts.jma)
uv run jma crawl --region Hangzhou --keywords "ai agent"
uv run pytest                            # full test suite (live tests skipped by default)
uv run pytest tests/domain               # one directory
uv run pytest tests/domain/test_dedup.py::test_name   # one test
uv run pytest -m live                    # opt-in: real network hits (TesterHome)
uv run ruff check .                      # lint
uv run ruff format .                     # format
```

`pytest.ini_options.addopts = "-m 'not live' -ra"` excludes the `live` marker by default — opt in explicitly when validating crawlers against the real site.

## Architecture

Data flows **inputs → sources → pipeline → storage**, with `domain/` as a pure island in the middle (frozen pydantic models, no I/O).

```
src/jma/
├── cli.py            Typer entrypoint. Resolves data_root, builds a per-source
│                     factory, calls pipeline.crawl.run, prints summary.
├── domain/           PURE. Frozen pydantic models, salary/exp/location parsers,
│                     dedup (canonical_id), blockage classifier. No network, no
│                     mutation, no logging.
├── sources/          One JobSource per site. base.py defines the Protocol +
│                     YAML SourceConfig loader; http.py is the rate-limited
│                     httpx wrapper; testerhome.py is the Phase-1 implementation.
├── pipeline/crawl.py Orchestrator. Opens DB, starts a Run, injects on_fetch /
│                     cache_get callbacks into the source factory, persists
│                     JobObservations + finishes the Run (even on exception).
└── storage/          SQLite (db.py — runs + jobs tables, WAL mode), gzipped
                      raw HTML blobs (blobs.py), 24h URL cache (cache.py).
```

**Source plug-in contract** (`sources/base.py`): a `JobSource` is anything with a `name` and an `async crawl(region, keywords, max_pages, max_jobs) -> SourceResult`. Per-site behavior is split between Python class + `config/sources/<name>.yaml` (selectors, URL template, rate limits). To add a source: drop a YAML file in `config/sources/`, write a class implementing the Protocol, and register a factory in `cli.py`.

**Why the factory-with-callbacks pattern** (`pipeline/crawl.py`): the pipeline owns the DB connection and URL cache, but the source owns the HTTP fetching. Callbacks (`on_fetch`, `cache_get`) let the source call back into storage without importing it. A probe-instance is built first to discover `source.name`, then the real instance is built with name-aware callbacks.

**SourceResult** is the universal return shape (`domain/models.py`). Every crawl outcome — ok, partial, blocked, empty, error — is one of these; the pipeline never raises blockage as an exception. `status=OK` + `reason="partial: stopped at page N (…)"` is the [[PartialHarvest]] convention from `CONTEXT.md`.

**Dedup model** (`docs/adr/0001`): the `jobs` table is keyed per-source (`sha1(source:internal_id)`) but every row also carries a `canonical_id = sha1(normalize(title|company|city))`. The same real Job seen via two sources is two rows sharing a `canonical_id`. **Any aggregation summarising "Jobs" (not "JobObservations") must `GROUP BY canonical_id`** — forgetting double-counts.

**Run lifecycle** (`docs/adr/0002`): every `jma crawl` invocation is a fresh Run row regardless of inputs. Same `(region, keywords)` run twice = two Runs. The `pipeline.crawl.run` wrapper always calls `finish_run` — including on unhandled exceptions — so no Run is ever left with `finished_at IS NULL`.

## Domain language

`CONTEXT.md` is the **canonical glossary** — [[Job]], [[JobObservation]], [[Run]], [[PartialHarvest]], [[SalaryDisclosure]], [[CrawlScope]], [[Source]]. Use these terms verbatim in issue titles, test names, and commit messages. Don't drift to synonyms. If a concept isn't in the glossary, that's a signal — either reconsider, or note it for a future `/grill-with-docs` session.

ADRs in `docs/adr/` record decisions that span multiple modules. If your change contradicts an ADR, surface it explicitly rather than silently overriding.

## Tests

Layout mirrors `src/jma/` — `tests/domain/`, `tests/sources/`, `tests/storage/`, `tests/pipeline/`, `tests/cli/`, plus `tests/live/` (opt-in). `pytest-asyncio` is in `auto` mode (`asyncio_mode = "auto"`), so `async def test_…` works without per-test markers. HTTP is mocked with `respx` in unit tests; the `live` marker is for real-network smoke tests.

## Ruff config

`pyproject.toml` selects `E, F, I, B, UP, SIM` with `line-length=100`, ignores `E501`. Per-file relaxations: tests waive `B` and `SIM`; `cli.py` waives `B008` (Typer's `Option(...)` default pattern).

## Style — follow user's global rules

Pure functions in `domain/`; effects live at the edges (`sources/`, `storage/`). Frozen pydantic models (`ConfigDict(frozen=True)`) — never mutate, always `model_copy(update=…)`. TDD applies: failing test first, then minimum code to pass. See user-global `CLAUDE.md` for the full ruleset.

## Runtime data

`data/` is gitignored except for its `.gitignore`. The CLI resolves it via `JMA_DATA_ROOT` env var, falling back to `./data/`. `data/jobs.db` is the SQLite store; `data/raw/<source>/<sha>.html.gz` holds raw blobs referenced by `Job.raw_payload_ref`.

## Workflow charts

Self-contained HTML diagrams in `docs/diagrams/`:

- [current-workflow.html](docs/diagrams/current-workflow.html) — the implemented Phase-0/1 crawl pipeline (cli → pipeline → source → storage).
- [plan-phases-workflow.html](docs/diagrams/plan-phases-workflow.html) — the full multi-phase plan from [PLAN.md](PLAN.md), showing where the current slice sits.

Open in a browser to see the rendered flow. Keep these in sync when the pipeline shape changes (new source, new stage, new storage layer).

## Agent infra (existing)

- **Issues**: GitHub on `snowshine0216/job-market-agent` via `gh` CLI — see [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).
- **Triage labels**: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` — see [docs/agents/triage-labels.md](docs/agents/triage-labels.md).
- **Domain docs**: single-context (`CONTEXT.md` + `docs/adr/` at repo root) — see [docs/agents/domain.md](docs/agents/domain.md).
