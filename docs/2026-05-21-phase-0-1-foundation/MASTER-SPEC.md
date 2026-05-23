# MASTER-SPEC — Phase 0 + Phase 1 Foundation

**Mode:** spec (single-feature, N=1)
**Run:** `docs/2026-05-21-phase-0-1-foundation/`
**Source:** [`docs/superpowers/specs/2026-05-21-phase-0-1-design.md`](../superpowers/specs/2026-05-21-phase-0-1-design.md)
**Date:** 2026-05-21

## Items

| # | Item | Status | Source file |
|---|------|--------|-------------|
| 001 | Phase 0 + Phase 1 — Foundation + TesterHome vertical slice | IN | [items/001-spec.md](items/001-spec.md) |

There are no OUT items; this is a single-feature spec run. See [SKIPPED.md](SKIPPED.md) (empty).

## Scope summary (verbatim from source spec §1)

**In scope**
- Project bootstrap: `pyproject.toml` via `uv`, `ruff`, `pytest`, `pytest-asyncio`, `respx`, `pydantic v2`, `httpx`, `selectolax`, `typer`, `aiosqlite`, `pyyaml`.
- Full v1 dataclasses in `domain/models.py` (`Job` + sub-objects, `SourceResult`, `MarketReport`, `FitReport`); frozen pydantic v2 models.
- `domain/normalize.py` (pure parsers), `domain/blockage.py` (pure HTTP + soft-block classifier), `domain/dedup.py` (`job_id` + `canonical_id`).
- `sources/base.py` (JobSource Protocol + SourceConfig loader), `sources/http.py` (httpx wrapper), `sources/testerhome.py` (first concrete source).
- `config/sources/testerhome.yaml`.
- `storage/db.py` (aiosqlite, schema bootstrap, `start_run`/`finish_run`/`insert_jobs`), `storage/cache.py` (24h URL cache), `storage/blobs.py` (gzipped raw HTML).
- `pipeline/crawl.py` (single-source orchestration), `cli.py` (`jma crawl …` only).

**Out of scope (deferred)**
- `randstad.py`, `bing.py`, `browser.py` (Phase 2).
- LLM client, extraction, narration (Phase 3+).
- `jma sources status`, `jma report …`, `jma run`, multi-source orchestration, `--concurrency` / `--delay-ms` flags (Phase 2+).
- `config/skills.yaml`, `config/region_aliases.yaml` (Phase 3 / 2).

The full spec — including the 15-row decision table, module layout, data model, SQLite schema, blockage classifier, TesterHome algorithm, CLI contract, testing strategy, exit criteria, TDD slice order (13 slices), and risk register — lives in [items/001-spec.md](items/001-spec.md).
