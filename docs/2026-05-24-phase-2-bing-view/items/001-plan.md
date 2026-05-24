# Phase 2 — Bing aggregator (SerpAPI) + `jma view` + TesterHome retirement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire TesterHome end-to-end and ship a single Bing-aggregator source via SerpAPI (snippet-only) plus a self-contained `jma view` static-HTML viewer of the latest finished Run. Add one per-Run column (`run_jobs.raw_payload_ref`) and one ADR (0005).

**Architecture:** New `sources/bing.py` issues SerpAPI calls (one blob per page, `.json.gz`), maps each organic result to a `Job` with `source=bing:<host>` (host = matched `target_sites` entry), and emits one [[JobObservation]] per row at `data_quality=0.4`. A new pure `report/view.py` builds a Jinja2 context from a Run + its jobs (per-Run blobs read from `run_jobs.raw_payload_ref`), and the new `cli.py view` subcommand writes one self-contained HTML file (inline CSS + ~30-line vanilla-JS sortable table). `SourceConfig` in `sources/base.py` is replaced (not extended) with the Bing-shaped model; the old TesterHome-shaped sub-models are deleted alongside the source. The DB is wiped manually pre-run so the new `run_jobs.raw_payload_ref NOT NULL` column lands migration-free.

**Tech Stack:** Python 3.12 + uv; `httpx` (SerpAPI fetches), `aiosqlite` (existing), `pydantic` v2 frozen models, `jinja2>=3.1` (NEW), `selectolax` (existing — used in `tests/report/test_view_template.py` to assert template structure), `typer` (existing CLI), `respx` (test HTTP mocking), `pytest` + `pytest-asyncio` auto mode.

---

## Scope notes (mandatory guards)

The spec's §1 splits scope into **In** and **Out of scope (deferred)**. This plan honors both verbatim.

### IN scope for this plan

1. **TesterHome retirement** — delete `src/jma/sources/testerhome.py`, `config/sources/testerhome.yaml`, four TesterHome-coupled test files, `tests/live/test_testerhome_live.py`, `docs/diagrams/phase-1-testerhome-crawl.html`. Flip CLI `--source` default to `["bing"]` and remove the `TesterHomeSource` import. Document `data/jobs.db` and `data/raw/testerhome/` wipe as a manual operator step.
2. **Bing aggregator (SerpAPI) — snippet-only.** `src/jma/sources/bing.py` + `config/sources/bing.yaml`. One blob per SerpAPI page (`.json.gz`). `source=bing:<host>` where `<host>` is the matched `target_sites` entry. `data_quality=0.4` for every row. `Location.city=None` for every row. Raw snippet stored in `description_text`.
3. **`jma view` CLI command** — renders one self-contained static HTML page (Jinja2) listing every observation in the latest finished Run, sortable client-side via inline JS, fixed default output `data/view.html`, `--open`/`--run`/`--out` flags. New module `src/jma/report/{view.py, templates/view.html.j2, __init__.py}`.
4. **One schema column** — `run_jobs.raw_payload_ref TEXT NOT NULL`. `jobs.raw_payload_ref` stays as latest-seen; `jobs_for_run` reads from `run_jobs.raw_payload_ref` for per-Run snapshot. Wipe + DDL change is migration-free.
5. **`SourceConfig` REPLACED** in `sources/base.py` — delete `ListingConfig`, `DetailConfig`, `content_block_markers`, `known_good_list_selector`, `base_url`. New shape: `name`, `engine`, `endpoint`, `api_key_env`, `target_sites`, `id_patterns`, `site_names`, `query_template`, `region_aliases`, `rate`. No discriminated union (YAGNI).
6. **Drop `--with-detail` CLI flag entirely** — TesterHome's `_factory_for` no longer applies. Phase 2 has no `--with-detail`; detail-fetch is deferred to Phase 2.1.
7. **PLAN.md / README.md / CLAUDE.md / CONTEXT.md edits** — per spec §5.4 and §9.
8. **Four diagram updates** — delete `phase-1-testerhome-crawl.html`; create `phase-2-bing-aggregator-crawl.html`; refresh `plan-phases-workflow.html`, `module-dependency.html`, `database-schema.html` in place.
9. **ADR-0005** — `docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md` per spec §10.
10. **`pyproject.toml`** — add `jinja2>=3.1` to `dependencies`. **Run `uv sync` before any `report/` tests can pass.**
11. **Company extraction is HEURISTIC ONLY** — generic `[|\-_]` delim-split, with per-host `site_names` YAML anchor for 2-part titles. Per-site **snippet** regexes remain forbidden. Per-site **URL** regexes via `id_patterns` are allowed (asymmetry locked in ADR-0005).
12. **Reserved `data_quality` values 0.7 / 0.9 / 1.0** are documented in ADR-0005 but unused in code in Phase 2.

### OUT of scope (DO NOT plan)

- Randstad direct crawler. Playwright fallback (`sources/browser.py`). LLM extraction (DeepSeek). `data/skills.yaml`. Market & fit reports. `jma run` wrapper. `jma sources status` health-check. `jma view` filtering / multi-run picker / aggregates panel. Direct BOSS Zhipin crawler. Live SerpAPI tests in CI (the `tests/live/test_bing_live.py` file exists but is opt-in via `-m live`). **Phase 2.1 detail-fetch enrichment** — no `--with-detail` flag, no `url_status` writes from bing in this phase.
- Any per-host **snippet** regex (forbidden by §2 row 8).
- A second `_factory_for` parameter for `with_detail` (the flag is gone).

### Test fixture provenance (one-time manual op)

The fixture `tests/fixtures/serpapi_bing_hangzhou_ai_agent.json` is **captured from one real SerpAPI call** by the operator during dev (spec §6 last paragraph; burns 1 quota credit). Sanitize before commit: strip `search_parameters.api_key`. Hand-trim to ≥3 hosts and ≥30 results, ensuring ≥1 row per host has a parseable salary in its `snippet`. **The bing-source tests in Task 8 cannot run green until this fixture is present** — Task 8 step 0 asserts its presence and halts the per-task loop with a clear message if it's missing.

---

## Step order overview

1. **Pre-work** — `uv sync` after adding `jinja2` to `pyproject.toml` so all later import-jinja2 tests work.
2. **Deletions first** — TesterHome source, config, four TesterHome-coupled test files, live test, phase-1 diagram. Drop CLI `--with-detail` and `TesterHome` import.
3. **Schema change** — `run_jobs.raw_payload_ref TEXT NOT NULL` in `_DDL`; update `insert_jobs`; add `latest_finished_run` + `jobs_for_run` helpers.
4. **`storage/blobs.py`** — add optional `suffix` parameter (default `.html.gz`).
5. **`SourceConfig` refactor** — replace the TesterHome-shaped model with the Bing-shaped one in `sources/base.py`.
6. **`config/sources/bing.yaml`** — write the YAML.
7. **`sources/bing.py`** — TDD: parser unit tests → company-heuristic tests → end-to-end mocked SerpAPI tests → implementation.
8. **`tests/live/test_bing_live.py`** — opt-in live smoke (only runs with `-m live`).
9. **`report/view.py` + template** — TDD: build_view_context unit test → template render assertions → implementation.
10. **`jma view` CLI** — TDD: empty-DB, finished-run, unknown-run, --open behavior → implementation.
11. **ADR-0005** — write `docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md`.
12. **Diagrams** — delete phase-1, create phase-2-bing-aggregator-crawl, refresh three existing.
13. **Docs** — `PLAN.md`, `README.md`, `CLAUDE.md`, `CONTEXT.md` edits.
14. **Final verification gate** — `uv run pytest -m 'not live'`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run jma view --help`, `uv run jma crawl --help`.

---

## File structure (at completion)

```
src/jma/
├── cli.py                                       # MODIFIED: drop --with-detail; bing factory; new view subcommand
├── domain/                                      # unchanged
├── sources/
│   ├── base.py                                  # MODIFIED: SourceConfig REPLACED (Bing-shaped)
│   ├── http.py                                  # unchanged
│   ├── bing.py                                  # NEW: BingAggregatorSource
│   └── testerhome.py                            # DELETED
├── pipeline/crawl.py                            # unchanged
├── storage/
│   ├── db.py                                    # MODIFIED: run_jobs.raw_payload_ref; helpers
│   ├── blobs.py                                 # MODIFIED: optional suffix= parameter
│   └── cache.py                                 # unchanged
└── report/                                      # NEW module
    ├── __init__.py
    ├── view.py
    └── templates/
        └── view.html.j2

config/sources/
├── bing.yaml                                    # NEW
└── testerhome.yaml                              # DELETED

tests/
├── sources/
│   ├── test_bing.py                             # NEW
│   ├── test_bing_company_heuristic.py           # NEW
│   ├── test_source_config.py                    # MODIFIED: now asserts Bing-shaped fields
│   ├── test_testerhome.py                       # DELETED
│   ├── test_testerhome_detail.py                # DELETED
│   ├── test_testerhome_with_detail.py           # DELETED
│   ├── test_detail_config_defaults.py           # DELETED (TesterHome-coupled)
│   ├── test_url_freshness.py                    # PORTED to bing fixture vehicle (helper relocated)
│   └── test_http.py                             # unchanged
├── storage/
│   ├── test_jobs_for_run.py                     # NEW
│   ├── test_db.py                               # unchanged
│   ├── test_db_migration.py                     # unchanged
│   ├── test_blobs.py                            # unchanged
│   └── test_cache.py                            # unchanged
├── report/                                      # NEW
│   ├── __init__.py
│   ├── test_view.py
│   └── test_view_template.py
├── cli/
│   ├── test_view.py                             # NEW
│   ├── test_cli.py                              # MODIFIED (drop with_detail expectations)
│   ├── test_crawl.py                            # MODIFIED (testerhome → bing)
│   └── test_summary.py                          # MODIFIED (testerhome → bing)
├── live/
│   ├── test_bing_live.py                        # NEW
│   └── test_testerhome_live.py                  # DELETED
├── pipeline/test_crawl_e2e.py                   # MODIFIED (use bing fake or remove TesterHome-only)
├── fixtures/
│   ├── serpapi_bing_hangzhou_ai_agent.json      # NEW (operator-captured)
│   └── sources/testerhome/                      # DELETED
└── ...

docs/
├── adr/0005-bing-aggregator-source-and-snippet-data-quality.md   # NEW
└── diagrams/
    ├── phase-1-testerhome-crawl.html            # DELETED
    ├── phase-2-bing-aggregator-crawl.html       # NEW
    ├── plan-phases-workflow.html                # MODIFIED
    ├── module-dependency.html                   # MODIFIED
    └── database-schema.html                     # MODIFIED

pyproject.toml                                   # MODIFIED: + jinja2>=3.1
PLAN.md                                          # MODIFIED (§1, §3, §4, §5, §6)
README.md                                        # MODIFIED (Phase status, examples, --source default, view subsection)
CLAUDE.md                                        # MODIFIED (Phase 2 reality, report/ in tree)
CONTEXT.md                                       # MODIFIED (audit; bing examples already present)
```

---

## Task 0: Pre-work — add `jinja2` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml` to add jinja2**

In `pyproject.toml`, locate the `[project]` block and add `"jinja2>=3.1"` to the `dependencies` list. Final shape:

```toml
[project]
name = "jma"
version = "0.1.0"
description = "Job-market-agent — TesterHome crawl vertical slice"
requires-python = ">=3.12"
dependencies = [
    "aiosqlite>=0.22.1",
    "httpx>=0.28.1",
    "jinja2>=3.1",
    "pydantic>=2.13.4",
    "pyyaml>=6.0.3",
    "selectolax>=0.4.9",
    "typer>=0.25.1",
]
```

- [ ] **Step 2: Resync the lockfile + venv**

Run: `uv sync`
Expected: jinja2 installs into `.venv/`, `uv.lock` is updated. No errors.

- [ ] **Step 3: Smoke-test the install**

Run: `uv run python -c "import jinja2; print(jinja2.__version__)"`
Expected: a version string `>= 3.1` prints, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add jinja2>=3.1 for jma view template rendering"
```

---

## Task 1: Delete TesterHome source code, YAML, and tests

**Files:**
- Delete: `src/jma/sources/testerhome.py`
- Delete: `config/sources/testerhome.yaml`
- Delete: `tests/sources/test_testerhome.py`
- Delete: `tests/sources/test_testerhome_detail.py`
- Delete: `tests/sources/test_testerhome_with_detail.py`
- Delete: `tests/sources/test_detail_config_defaults.py`  (TesterHome-coupled; imports `DetailConfig` which we will delete)
- Delete: `tests/live/test_testerhome_live.py`
- Delete: `tests/fixtures/sources/testerhome/` (entire directory)
- Delete: `docs/diagrams/phase-1-testerhome-crawl.html`

The decision on `tests/sources/test_url_freshness.py` is deferred to Task 6 — it imports `_apply_url_freshness` from `jma.sources.testerhome` which goes away with the deletion. We **port the helper** (not the test) into Phase 2 only if a future detail-fetch path needs it. Per spec §5.2 grep-first policy: the test exercises a *generic helper* via TesterHome as a vehicle, but the helper itself is currently dead code in Phase 2 (no detail-fetch). **Decision:** delete the test in this task; the helper code goes away with `sources/testerhome.py`. ADR-0005 notes that when Phase 2.1 re-introduces detail-fetch, `_apply_url_freshness` is reborn (in `sources/bing.py`) with its tests re-ported. Also delete: `tests/sources/test_url_freshness.py`.

- [ ] **Step 1: Grep-first sanity check on the deletions**

Run: `grep -rn "from jma.sources.testerhome\|import jma.sources.testerhome\|TesterHomeSource" src tests --include='*.py' || true`

Expected: matches in `src/jma/cli.py` (1 import), `tests/sources/test_testerhome*.py`, `tests/sources/test_url_freshness.py`, `tests/sources/test_detail_config_defaults.py`. Note matches in `tests/cli/*.py` or `tests/pipeline/*.py` for follow-up in Task 12. **If any non-test, non-cli match is found outside this list, halt and report.**

Run: `grep -rn "testerhome" tests/ docs/ --include='*.py' --include='*.md' --include='*.html' --include='*.yaml' || true`

Expected: TesterHome references in CLI tests, pipeline e2e test, README, PLAN.md, CLAUDE.md, CONTEXT.md, and diagram HTMLs. These are handled in later tasks; record the count for cross-check.

- [ ] **Step 2: Delete the files**

```bash
rm src/jma/sources/testerhome.py
rm config/sources/testerhome.yaml
rm tests/sources/test_testerhome.py
rm tests/sources/test_testerhome_detail.py
rm tests/sources/test_testerhome_with_detail.py
rm tests/sources/test_detail_config_defaults.py
rm tests/sources/test_url_freshness.py
rm tests/live/test_testerhome_live.py
rm -rf tests/fixtures/sources/testerhome
rm docs/diagrams/phase-1-testerhome-crawl.html
```

- [ ] **Step 3: Verify deletions**

Run: `ls src/jma/sources/ config/sources/ tests/sources/ tests/live/ tests/fixtures/sources/ docs/diagrams/ 2>&1 | grep -i testerhome || echo "no testerhome leftovers"`

Expected: `no testerhome leftovers`.

- [ ] **Step 4: Commit (intermediate — will be red until Tasks 2–7 land)**

```bash
git add -A
git commit -m "feat(phase-2): retire TesterHome — delete source, YAML, tests, live test, phase-1 diagram"
```

> **Note:** the repo is intentionally red at this commit (`cli.py` still imports `TesterHomeSource`). The next task fixes that. Frequent commits per project convention.

---

## Task 2: Strip TesterHome wiring from `cli.py` (no view subcommand yet)

**Files:**
- Modify: `src/jma/cli.py`

We make `cli.py` import-clean and runnable in isolation: drop the `TesterHomeSource` import, drop `_factory_for`'s `with_detail` parameter and body, drop the `--with-detail` Typer Option, drop the TesterHome `--source` default. We **do not** wire the bing factory yet — Task 8 will. This leaves `--source bing` exiting non-zero with `KeyError`/`FileNotFoundError`, which is fine; pytest only runs CLI tests after Task 12.

- [ ] **Step 1: Replace `cli.py` top imports**

Edit `src/jma/cli.py`:

Replace:
```python
from jma.sources.testerhome import TesterHomeSource
```
with nothing (delete the line entirely).

- [ ] **Step 2: Replace `_factory_for`**

Replace the entire `_factory_for` function body. Old:

```python
def _factory_for(source_name: str, data_root: Path, with_detail: bool):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")
    if with_detail:
        cfg = cfg.model_copy(update={"detail": cfg.detail.model_copy(update={"enabled": True})})

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        return TesterHomeSource(
            cfg=cfg, http=http, data_root=data_root, on_fetch=on_fetch, cache_get=cache_get
        )

    return _make
```

New (Bing-only factory; raises `KeyError` for any unknown source name):

```python
def _factory_for(source_name: str, data_root: Path):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")
    if source_name == "bing":
        # Lazy import so `jma view` works even if jma.sources.bing has a syntax-time issue.
        from jma.sources.bing import BingAggregatorSource

        def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
            http = AsyncHttpClient(ac, rate=cfg.rate)
            return BingAggregatorSource(
                cfg=cfg, http=http, data_root=data_root, on_fetch=on_fetch, cache_get=cache_get
            )

        return _make
    raise KeyError(f"unknown source: {source_name!r}")
```

- [ ] **Step 3: Replace the `crawl` command signature + body**

In the `@app.command()` `crawl(...)` definition, change:

- `source: list[str] = typer.Option(["testerhome"], "--source", help="Source name (repeatable).")` → `source: list[str] = typer.Option(["bing"], "--source", help="Source name (repeatable).")`
- Delete the entire `with_detail: bool = typer.Option(...)` parameter (including its docstring help block).
- Delete the call-site `with_detail=with_detail` argument from `_factory_for(s_name, data_root, with_detail=with_detail)`. Final call: `source_factory=_factory_for(s_name, data_root)`.

Also add a fail-fast `SERPAPI_KEY` check at the very top of `crawl(...)`'s body, *after* `logging.basicConfig(...)` and *before* `keywords_t = tuple(keywords)`:

```python
    # Fail fast on missing env vars required by selected sources (spec §2 row 9).
    _check_required_env_for_sources(source)
```

And add the helper near the top of the module (after `_data_root`):

```python
def _check_required_env_for_sources(source_names: list[str]) -> None:
    """Raise typer.Exit(1) with a clear message if any selected source's
    api_key_env is unset. Runs after Typer arg parsing, before the DB opens
    (spec §2 row 9). Pure on env state."""
    for name in source_names:
        try:
            cfg = load_source_config(_CFG_DIR / f"{name}.yaml")
        except FileNotFoundError:
            continue  # _factory_for will raise a clearer error later
        env_name = getattr(cfg, "api_key_env", None)
        if env_name and not os.environ.get(env_name):
            typer.echo(
                f"missing env var {env_name} (required by source {name!r})", err=True
            )
            raise typer.Exit(code=1)
```

- [ ] **Step 4: Verify `cli.py` parses**

Run: `uv run python -c "import jma.cli; print(jma.cli.app)"`
Expected: prints `<typer.main.Typer object at 0x...>` and exits 0. Any `ImportError` means a residual TesterHome reference — grep and fix.

- [ ] **Step 5: Commit**

```bash
git add src/jma/cli.py
git commit -m "feat(cli): drop TesterHome import + --with-detail; default --source bing; fail fast on missing SERPAPI_KEY"
```

---

## Task 3: Replace `SourceConfig` in `sources/base.py` with the Bing-shaped model

**Files:**
- Modify: `src/jma/sources/base.py`
- Modify: `tests/sources/test_source_config.py` (rewrite to assert Bing shape via bing.yaml)

We delete the TesterHome-shaped sub-models and replace `SourceConfig` with the Bing-shaped one. `RateConfig` survives unchanged (it's source-agnostic and `http.py` already imports it).

- [ ] **Step 1: Write the failing `test_source_config.py` rewrite**

Replace the entire contents of `tests/sources/test_source_config.py` with:

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jma.sources.base import JobSource, SourceConfig, load_source_config

REPO = Path(__file__).resolve().parents[2]


def test_loads_bing_yaml() -> None:
    cfg = load_source_config(REPO / "config/sources/bing.yaml")
    assert isinstance(cfg, SourceConfig)
    assert cfg.name == "bing"
    assert cfg.engine == "bing"
    assert cfg.endpoint == "https://serpapi.com/search"
    assert cfg.api_key_env == "SERPAPI_KEY"
    assert cfg.results_per_query == 50
    # Hosts that ship as targets in Phase 2.
    assert "zhipin.com" in cfg.target_sites
    assert "lagou.com" in cfg.target_sites
    assert "liepin.com" in cfg.target_sites
    assert "51job.com" in cfg.target_sites
    assert "zhaopin.com" in cfg.target_sites
    # URL-pattern map: zhipin + liepin populated; others intentionally absent.
    assert cfg.id_patterns["zhipin.com"] == r"/job_detail/(\d+)\.html"
    assert cfg.id_patterns["liepin.com"] == r"/job/(\d+)\.html"
    assert "lagou.com" not in cfg.id_patterns
    # Site-name map for the company heuristic.
    assert cfg.site_names["zhipin.com"] == "BOSS直聘"
    assert cfg.site_names["liepin.com"] == "猎聘"
    # Query template is multi-line YAML; key tokens present.
    assert "{keywords}" in cfg.query_template
    assert "{region_variants}" in cfg.query_template
    assert "{site_clause}" in cfg.query_template
    # Region aliases — Hangzhou variant set.
    assert cfg.region_aliases["Hangzhou"] == ["Hangzhou", "杭州", "杭州市"]
    # Rate config carries through unchanged.
    assert cfg.rate.delay_ms == 800
    assert cfg.rate.max_retries == 3


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "x"}))  # no engine, endpoint, etc.
    with pytest.raises(ValidationError):
        load_source_config(bad)


def test_jobsource_protocol_runtime_checkable() -> None:
    class _Fake:
        name = "fake"

        async def crawl(self, region, keywords, max_pages, max_jobs):
            return None

    assert isinstance(_Fake(), JobSource)
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/sources/test_source_config.py -q`
Expected: FAIL — `SourceConfig` is still TesterHome-shaped, no `engine` / `endpoint` / `api_key_env` fields. Plus `config/sources/bing.yaml` does not exist yet.

- [ ] **Step 3: Replace `sources/base.py` with the Bing-shaped model**

Replace the entire contents of `src/jma/sources/base.py` with:

```python
"""JobSource Protocol + SourceConfig loader (Phase 2: Bing-shaped).

The old TesterHome-shaped SourceConfig (with ListingConfig / DetailConfig /
content_block_markers / known_good_list_selector / base_url) was deleted
when TesterHomeSource was retired in Phase 2. A discriminated-union shape
(direct: DirectCrawlConfig | None + aggregator: AggregatorConfig | None)
is deferred until a second source ships that genuinely needs both branches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict

from jma.domain.models import SourceResult


class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2
    max_retries_5xx: int = 1


class SourceConfig(BaseModel):
    """Bing-aggregator shape. See config/sources/bing.yaml."""

    model_config = ConfigDict(frozen=True)
    name: str
    engine: str
    endpoint: str
    api_key_env: str
    results_per_query: int = 50
    target_sites: tuple[str, ...]
    id_patterns: dict[str, str] = {}
    site_names: dict[str, str] = {}
    query_template: str
    region_aliases: dict[str, list[str]] = {}
    rate: RateConfig = RateConfig()


def load_source_config(path: str | Path) -> SourceConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SourceConfig.model_validate(raw)


@runtime_checkable
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

- [ ] **Step 4: Verify the file imports cleanly**

Run: `uv run python -c "from jma.sources.base import SourceConfig, RateConfig, JobSource, load_source_config; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/base.py tests/sources/test_source_config.py
git commit -m "feat(sources): replace SourceConfig with Bing-shaped model; drop TesterHome sub-models"
```

> The new test still fails (no `bing.yaml`). Task 4 lands the YAML.

---

## Task 4: Write `config/sources/bing.yaml`

**Files:**
- Create: `config/sources/bing.yaml`

- [ ] **Step 1: Write the YAML file**

Create `config/sources/bing.yaml` with this exact content (matches spec §3.2 verbatim, with quoted regex patterns to keep YAML happy):

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

- [ ] **Step 2: Run `test_source_config.py` — should now pass**

Run: `uv run pytest tests/sources/test_source_config.py -q`
Expected: `3 passed`.

- [ ] **Step 3: Commit**

```bash
git add config/sources/bing.yaml
git commit -m "feat(config): add bing.yaml — SerpAPI engine, target_sites, id_patterns, site_names"
```

---

## Task 5: Add `run_jobs.raw_payload_ref` and per-Run query helpers

**Files:**
- Modify: `src/jma/storage/db.py`
- Create: `tests/storage/test_jobs_for_run.py`

We write the test first (red), then change `_DDL` + `insert_jobs` + add `latest_finished_run` + `jobs_for_run` (green). The wipe in Task 13 makes this migration-free for fresh DBs; the existing `_apply_jobs_migrations` block does NOT cover `run_jobs` migrations, so existing DBs would break — that's by design per spec §2 row 16 (the wipe is the migration story).

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_jobs_for_run.py`:

```python
"""Per-Run snapshot of raw_payload_ref via run_jobs.raw_payload_ref (spec §2 row 17)."""

from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite
import pytest

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary
from jma.storage.db import (
    finish_run,
    insert_jobs,
    jobs_for_run,
    latest_finished_run,
    open_db,
    start_run,
)


def _job(
    *,
    iid: str,
    blob: str,
    posted_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> Job:
    return Job(
        id=job_id(source="bing:zhipin.com", internal_id=iid, title="t", company=None, city=None),
        canonical_id=canonical_id(title="t", company=None, city=None),
        source="bing:zhipin.com",
        source_internal_id=iid,
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        posted_at=posted_at,
        fetched_at=fetched_at or datetime(2026, 5, 24, 0, 0, 0, tzinfo=UTC),
        url=f"https://x/{iid}",
        raw_payload_ref=blob,
    )


@pytest.mark.asyncio
async def test_jobs_for_run_returns_per_run_blob_ref(tmp_path):
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        run_a = await start_run(conn, region="r", keywords=("k",))
        await insert_jobs(conn, run_a, [_job(iid="1", blob="raw/bing/20260524/blob_a.json.gz")])
        await finish_run(conn, run_id=run_a, source_results=[])

        run_b = await start_run(conn, region="r", keywords=("k",))
        # Same job id (same source + internal_id) re-observed in Run B with a different blob.
        await insert_jobs(conn, run_b, [_job(iid="1", blob="raw/bing/20260524/blob_b.json.gz")])
        await finish_run(conn, run_id=run_b, source_results=[])

        a_rows = await jobs_for_run(conn, run_a)
        b_rows = await jobs_for_run(conn, run_b)

    assert len(a_rows) == 1
    assert len(b_rows) == 1
    assert a_rows[0].raw_payload_ref == "raw/bing/20260524/blob_a.json.gz"
    assert b_rows[0].raw_payload_ref == "raw/bing/20260524/blob_b.json.gz"


@pytest.mark.asyncio
async def test_jobs_for_run_orders_posted_desc_nulls_last_fetched_desc(tmp_path):
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        run_id = await start_run(conn, region="r", keywords=("k",))
        t0 = datetime(2026, 5, 20, 0, 0, 0, tzinfo=UTC)
        await insert_jobs(
            conn,
            run_id,
            [
                _job(iid="A", blob="a.gz", posted_at=None, fetched_at=t0),
                _job(
                    iid="B",
                    blob="b.gz",
                    posted_at=datetime(2026, 5, 22, tzinfo=UTC),
                    fetched_at=t0,
                ),
                _job(
                    iid="C",
                    blob="c.gz",
                    posted_at=datetime(2026, 5, 23, tzinfo=UTC),
                    fetched_at=t0,
                ),
                _job(
                    iid="D",
                    blob="d.gz",
                    posted_at=None,
                    fetched_at=datetime(2026, 5, 21, tzinfo=UTC),
                ),
            ],
        )
        await finish_run(conn, run_id=run_id, source_results=[])
        rows = await jobs_for_run(conn, run_id)

    ids = [r.source_internal_id for r in rows]
    # posted DESC: C (2026-05-23), B (2026-05-22), then NULLS LAST with
    # fetched DESC tiebreak between D (fetched 2026-05-21) and A (2026-05-20).
    assert ids == ["C", "B", "D", "A"]


@pytest.mark.asyncio
async def test_latest_finished_run_returns_most_recent(tmp_path):
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        unfinished = await start_run(conn, region="r", keywords=("k",))
        finished_old = await start_run(conn, region="r", keywords=("k",))
        await finish_run(conn, run_id=finished_old, source_results=[])
        finished_new = await start_run(conn, region="r", keywords=("k",))
        await finish_run(conn, run_id=finished_new, source_results=[])

        latest = await latest_finished_run(conn)

    assert latest is not None
    assert latest.id == finished_new
    assert unfinished != latest.id  # unfinished is ignored


@pytest.mark.asyncio
async def test_latest_finished_run_returns_none_on_empty_db(tmp_path):
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        latest = await latest_finished_run(conn)
    assert latest is None


@pytest.mark.asyncio
async def test_jobs_for_run_unknown_run_returns_empty(tmp_path):
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        rows = await jobs_for_run(conn, "deadbeef" * 4)
    assert rows == []


@pytest.mark.asyncio
async def test_run_jobs_raw_payload_ref_column_exists(tmp_path):
    """Sanity check: the new column lands on schema create, not migration."""
    db_path = tmp_path / "jobs.db"
    ctx = await open_db(db_path)
    async with ctx as conn:
        cur = await conn.execute("PRAGMA table_info(run_jobs)")
        cols = [row[1] for row in await cur.fetchall()]
    assert "raw_payload_ref" in cols
```

- [ ] **Step 2: Run the test — confirm it fails**

Run: `uv run pytest tests/storage/test_jobs_for_run.py -q`
Expected: FAIL — `jobs_for_run`, `latest_finished_run`, and the `Run` import target don't exist; `run_jobs.raw_payload_ref` column missing.

- [ ] **Step 3: Add `Run` dataclass to `domain/models.py`**

Append to `src/jma/domain/models.py` (after the existing classes):

```python
class Run(BaseModel):
    """A single execution of `jma crawl`. See CONTEXT.md [[Run]]."""

    model_config = ConfigDict(frozen=True)

    id: str
    region: str
    keywords: tuple[str, ...]
    started_at: datetime
    finished_at: datetime | None = None
```

- [ ] **Step 4: Update `_DDL` and `insert_jobs` in `storage/db.py`**

In `src/jma/storage/db.py`, change the `run_jobs` table definition in `_DDL`. Old:

```sql
CREATE TABLE IF NOT EXISTS run_jobs (
    run_id    TEXT NOT NULL REFERENCES runs(id),
    job_id    TEXT NOT NULL REFERENCES jobs(id),
    PRIMARY KEY (run_id, job_id)
);
```

New:

```sql
CREATE TABLE IF NOT EXISTS run_jobs (
    run_id          TEXT NOT NULL REFERENCES runs(id),
    job_id          TEXT NOT NULL REFERENCES jobs(id),
    raw_payload_ref TEXT NOT NULL,
    PRIMARY KEY (run_id, job_id)
);
```

In `insert_jobs`, change the `run_jobs` insert. Old:

```python
    await conn.executemany(
        "INSERT OR IGNORE INTO run_jobs (run_id, job_id) VALUES (?, ?)",
        [(run_id, row[0]) for row in rows],
    )
```

New (carry the blob ref from each Job onto the per-Run join row):

```python
    await conn.executemany(
        "INSERT OR IGNORE INTO run_jobs (run_id, job_id, raw_payload_ref) VALUES (?, ?, ?)",
        [(run_id, j.id, j.raw_payload_ref) for j in jobs],
    )
```

Note: this replaces the iteration variable from `row` (tuple) to `j` (Job). Confirm the surrounding `rows = [_job_to_row(j) for j in jobs]` and `if not rows: return` lines are untouched; we still need `rows` for the `jobs` table executemany.

- [ ] **Step 5: Add `latest_finished_run` and `jobs_for_run` helpers**

Append to `src/jma/storage/db.py`:

```python
def _row_to_job(row: tuple, run_blob_ref: str) -> Job:
    """Hydrate a Job from a jobs-table row.

    `run_blob_ref` is the per-Run raw_payload_ref from run_jobs, used in
    place of the row's latest-seen jobs.raw_payload_ref so the view links
    to the blob captured during *that* Run (spec §2 row 17).
    """
    from jma.domain.models import (  # local import: avoid widening module imports
        Experience,
        Job,
        Location,
        Salary,
        SalaryPeriod,
        Seniority,
        UrlStatus,
        WorkMode,
    )

    (
        id_,
        canonical_id_,
        source,
        source_internal_id,
        title,
        title_raw,
        company,
        location_country,
        location_city,
        location_district,
        location_work_mode,
        salary_min,
        salary_max,
        salary_currency,
        salary_period,
        salary_months_per_year,
        salary_raw,
        salary_parsed,
        experience_min_years,
        experience_max_years,
        experience_raw,
        skills_raw_json,
        skills_canonical_json,
        seniority,
        responsibilities_summary,
        description_text,
        posted_at,
        fetched_at,
        url,
        _jobs_raw_payload_ref,  # latest-seen on jobs; we override with the per-Run value
        data_quality,
        url_status,
        url_last_checked_at,
    ) = row
    return Job(
        id=id_,
        canonical_id=canonical_id_,
        source=source,
        source_internal_id=source_internal_id,
        title=title,
        title_raw=title_raw,
        company=company,
        location=Location(
            country=location_country,
            city=location_city,
            district=location_district,
            work_mode=WorkMode(location_work_mode),
        ),
        salary=Salary(
            min=salary_min,
            max=salary_max,
            currency=salary_currency,
            period=SalaryPeriod(salary_period),
            months_per_year=salary_months_per_year,
            raw=salary_raw,
            parsed=bool(salary_parsed),
        ),
        experience=Experience(
            min_years=experience_min_years,
            max_years=experience_max_years,
            raw=experience_raw,
        ),
        skills_raw=json.loads(skills_raw_json),
        skills_canonical=json.loads(skills_canonical_json),
        seniority=Seniority(seniority),
        responsibilities_summary=responsibilities_summary,
        description_text=description_text,
        posted_at=datetime.fromisoformat(posted_at) if posted_at else None,
        fetched_at=datetime.fromisoformat(fetched_at),
        url=url,
        raw_payload_ref=run_blob_ref,
        data_quality=data_quality,
        url_status=UrlStatus(url_status),
        url_last_checked_at=(
            datetime.fromisoformat(url_last_checked_at) if url_last_checked_at else None
        ),
    )


# Order: posted_at DESC NULLS LAST, fetched_at DESC. NULLS LAST requires
# SQLite 3.30+ (2019). Spec §3.5 second-to-last bullet.
_SELECT_JOBS_FOR_RUN = """
SELECT j.*, rj.raw_payload_ref AS run_blob
FROM jobs j
JOIN run_jobs rj ON rj.job_id = j.id
WHERE rj.run_id = ?
ORDER BY j.posted_at DESC NULLS LAST, j.fetched_at DESC
"""


async def jobs_for_run(conn: aiosqlite.Connection, run_id: str) -> list[Job]:
    cur = await conn.execute(_SELECT_JOBS_FOR_RUN, (run_id,))
    rows = await cur.fetchall()
    # Each row has 33 jobs-table columns followed by run_blob (the per-Run ref).
    jobs: list[Job] = []
    for r in rows:
        run_blob = r[-1]
        jobs_columns = tuple(r[:-1])
        jobs.append(_row_to_job(jobs_columns, run_blob_ref=run_blob))
    return jobs


async def latest_finished_run(conn: aiosqlite.Connection) -> "Run | None":
    from jma.domain.models import Run  # local import

    cur = await conn.execute(
        "SELECT id, region, keywords_json, started_at, finished_at "
        "FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY started_at DESC LIMIT 1"
    )
    row = await cur.fetchone()
    if row is None:
        return None
    return Run(
        id=row[0],
        region=row[1],
        keywords=tuple(json.loads(row[2])),
        started_at=datetime.fromisoformat(row[3]),
        finished_at=datetime.fromisoformat(row[4]),
    )


async def get_run(conn: aiosqlite.Connection, run_id: str) -> "Run | None":
    """Fetch a Run by id; finished_at may be None."""
    from jma.domain.models import Run

    cur = await conn.execute(
        "SELECT id, region, keywords_json, started_at, finished_at FROM runs WHERE id = ?",
        (run_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    return Run(
        id=row[0],
        region=row[1],
        keywords=tuple(json.loads(row[2])),
        started_at=datetime.fromisoformat(row[3]),
        finished_at=datetime.fromisoformat(row[4]) if row[4] else None,
    )
```

- [ ] **Step 6: Run the test again — confirm green**

Run: `uv run pytest tests/storage/test_jobs_for_run.py -q`
Expected: `6 passed`.

- [ ] **Step 7: Re-run existing storage tests to confirm no regression**

Run: `uv run pytest tests/storage/ -q`
Expected: all storage tests pass (the existing `test_db.py` / `test_blobs.py` / `test_cache.py` / `test_db_migration.py` cover the unchanged surface).

> **If `test_db_migration.py` fails on an existing test DB:** the only call to `insert_jobs` in existing tests goes through the new `(run_id, job_id, raw_payload_ref)` tuple. Existing tests build `Job` instances with `raw_payload_ref` set, so they should pass. If they don't, inspect the failure and fix call sites; do not bypass the NOT NULL constraint.

- [ ] **Step 8: Commit**

```bash
git add src/jma/domain/models.py src/jma/storage/db.py tests/storage/test_jobs_for_run.py
git commit -m "feat(storage): add run_jobs.raw_payload_ref + jobs_for_run/latest_finished_run helpers"
```

---

## Task 6: Add optional `suffix=` parameter to `blobs.write`

**Files:**
- Modify: `src/jma/storage/blobs.py`
- Modify: `tests/storage/test_blobs.py` (add a `.json.gz` suffix test)

The bing source writes SerpAPI JSON, not HTML — so it needs `.json.gz`. Existing callers (zero after Task 1) default to `.html.gz`.

- [ ] **Step 1: Write the failing test addition**

Append to `tests/storage/test_blobs.py` (do **not** replace existing tests; they cover the default suffix):

```python
def test_write_with_json_gz_suffix(tmp_path):
    """Bing source writes SerpAPI JSON page payloads with .json.gz (spec §3.6, §5.4)."""
    ref = blobs.write(
        root=tmp_path,
        source="bing",
        url="https://serpapi.com/search?q=foo&start=0",
        body='{"organic_results":[]}',
        suffix=".json.gz",
    )
    assert ref.endswith(".json.gz")
    assert "/raw/bing/" in ref
    # Round-trip read.
    assert blobs.read(root=tmp_path, ref=ref) == '{"organic_results":[]}'
```

If `tests/storage/test_blobs.py` does not import `blobs` at the top, run `head tests/storage/test_blobs.py` first and adapt the import; the new test only uses `blobs.write` and `blobs.read`.

- [ ] **Step 2: Run the test — confirm it fails**

Run: `uv run pytest tests/storage/test_blobs.py::test_write_with_json_gz_suffix -q`
Expected: FAIL — `write()` rejects `suffix` keyword argument.

- [ ] **Step 3: Update `blobs.write` to accept `suffix`**

In `src/jma/storage/blobs.py`, change `_ref()` and `write()`:

Old `_ref`:
```python
def _ref(source: str, url: str, when: datetime) -> str:
    ymd = when.astimezone(UTC).strftime("%Y%m%d")
    return f"raw/{source}/{ymd}/{_sha1_short(url)}.html.gz"
```

New `_ref`:
```python
def _ref(source: str, url: str, when: datetime, suffix: str) -> str:
    ymd = when.astimezone(UTC).strftime("%Y%m%d")
    return f"raw/{source}/{ymd}/{_sha1_short(url)}{suffix}"
```

Old `write`:
```python
def write(
    *,
    root: str | Path,
    source: str,
    url: str,
    body: str,
    now: datetime | None = None,
) -> str:
    when = now or datetime.now(UTC)
    ref = _ref(source, url, when)
    full = Path(root) / ref
    full.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(full, "wb") as f:
        f.write(body.encode("utf-8"))
    return ref
```

New `write`:
```python
def write(
    *,
    root: str | Path,
    source: str,
    url: str,
    body: str,
    suffix: str = ".html.gz",
    now: datetime | None = None,
) -> str:
    when = now or datetime.now(UTC)
    ref = _ref(source, url, when, suffix)
    full = Path(root) / ref
    full.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(full, "wb") as f:
        f.write(body.encode("utf-8"))
    return ref
```

- [ ] **Step 4: Run the full blobs test file — confirm all green**

Run: `uv run pytest tests/storage/test_blobs.py -q`
Expected: all tests pass (existing default-suffix tests and the new one).

- [ ] **Step 5: Commit**

```bash
git add src/jma/storage/blobs.py tests/storage/test_blobs.py
git commit -m "feat(blobs): add optional suffix= parameter (default .html.gz) for bing JSON blobs"
```

---

## Task 7: Bing company-extraction heuristic (TDD)

**Files:**
- Create: `tests/sources/test_bing_company_heuristic.py`
- Modify: `src/jma/sources/bing.py` (just enough to host the helper — the full source lands in Task 8)

Per spec §2 row 8: heuristic-only, with per-host `site_names` YAML anchor. **No per-site snippet regex.** We start by creating `bing.py` as a stub holding only the heuristic helper; Task 8 builds the source class around it.

- [ ] **Step 1: Write the failing parameterised test**

Create `tests/sources/test_bing_company_heuristic.py`:

```python
"""Company extraction heuristic for Bing-aggregator titles (spec §2 row 8)."""

from __future__ import annotations

import pytest

from jma.sources.bing import _heuristic_company_from_title


@pytest.mark.parametrize(
    "title,site_name,expected",
    [
        # 3-part: middle wins regardless of tail.
        ("AI Agent 工程师 - 阿里巴巴 - BOSS直聘", "BOSS直聘", "阿里巴巴"),
        # 2-part, segment_2 ≠ site_name → company.
        ("AI Engineer | NetEase", "BOSS直聘", "NetEase"),
        # 2-part, segment_2 == site_name → drop (locks in the site-name anchor).
        ("AI Agent | 拉勾招聘", "拉勾招聘", None),
        # 1-part: no delimiter, no signal.
        ("AI Agent 后端", "BOSS直聘", None),
        # No site_name available (host without site_names entry) — segment_2 wins.
        ("AI Engineer | NetEase", None, "NetEase"),
        # Underscore delimiter also splits.
        ("AI Engineer_NetEase_BOSS直聘", "BOSS直聘", "NetEase"),
        # Em-dash variant (we only split on [|\-_]; em-dash is not a delim → 1-part).
        ("AI Engineer — NetEase", "BOSS直聘", None),
        # Whitespace around delim is trimmed in segments.
        ("  AI Engineer   |   NetEase  ", "BOSS直聘", "NetEase"),
    ],
)
def test_company_heuristic_cases(title: str, site_name: str | None, expected: str | None) -> None:
    assert _heuristic_company_from_title(title, site_name) == expected
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/sources/test_bing_company_heuristic.py -q`
Expected: FAIL — `jma.sources.bing` does not exist yet.

- [ ] **Step 3: Create `src/jma/sources/bing.py` stub with just the heuristic**

Create `src/jma/sources/bing.py` with only the heuristic for now (the full source class lands in Task 8):

```python
"""BingAggregatorSource — SerpAPI-backed Bing search across configured job boards.

Phase 2: snippet-only mapping (no detail-fetch). See docs/2026-05-24-phase-2-bing-view/
items/001-spec.md §§3.1–3.6 and docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md.
"""

from __future__ import annotations

import re

# Heuristic-only company extraction. Per-site snippet regexes are forbidden
# (spec §2 row 8). The only per-host knob is `site_names` from bing.yaml,
# used to recognise the board's own name in 2-part titles like
# "AI Agent | BOSS直聘" so we drop it rather than mis-extract it as a company.
_DELIM_SPLIT = re.compile(r"\s*[|\-_]\s*")


def _heuristic_company_from_title(title: str, site_name: str | None) -> str | None:
    """Return the heuristic company name or None.

    - 3-part title (`role DELIM company DELIM site_tail`): the middle segment wins.
    - 2-part title (`role DELIM segment_2`):
        - if site_name is set AND segment_2 == site_name → return None
        - else → return segment_2 as the company.
    - 1-part title (no delimiter) → None.
    """
    parts = [p.strip() for p in _DELIM_SPLIT.split(title.strip()) if p.strip()]
    if len(parts) >= 3:
        return parts[1]
    if len(parts) == 2:
        segment_2 = parts[1]
        if site_name is not None and segment_2 == site_name:
            return None
        return segment_2
    return None
```

- [ ] **Step 4: Run the test — confirm green**

Run: `uv run pytest tests/sources/test_bing_company_heuristic.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/bing.py tests/sources/test_bing_company_heuristic.py
git commit -m "feat(sources/bing): add company-extraction heuristic with site_name anchor"
```

---

## Task 8: BingAggregatorSource — end-to-end source class (TDD)

**Files:**
- Create: `tests/fixtures/serpapi_bing_hangzhou_ai_agent.json`  (operator-captured; see Step 0)
- Create: `tests/sources/test_bing.py`
- Modify: `src/jma/sources/bing.py` (full source class)

This is the largest task. We write the test against the operator-captured fixture, then implement the source. We use `respx` to mock `https://serpapi.com/search?...`, returning the fixture JSON.

- [ ] **Step 0: Operator gate — confirm fixture present**

```bash
test -f tests/fixtures/serpapi_bing_hangzhou_ai_agent.json && echo OK || echo MISSING
```

If MISSING: **halt the task loop.** The fixture must be captured by the operator/orchestrator from one real SerpAPI call (see spec §6 last paragraph). Run:

```bash
SERPAPI_KEY=... curl 'https://serpapi.com/search' \
  --data-urlencode 'engine=bing' \
  --data-urlencode 'q=("AI agent") (Hangzhou OR 杭州 OR 杭州市) (site:zhipin.com OR site:lagou.com OR site:liepin.com OR site:51job.com OR site:zhaopin.com) (招聘 OR hiring OR JD) -inurl:resume' \
  --data-urlencode 'api_key=$SERPAPI_KEY' \
  --data-urlencode 'count=50' \
  -G > tests/fixtures/serpapi_bing_hangzhou_ai_agent.json
```

Sanitize: open the file, delete the `search_parameters.api_key` field if present, trim `organic_results` to ≥30 entries spanning ≥3 hosts (zhipin, lagou, liepin at minimum), and confirm ≥1 row per host has a snippet containing a parseable salary token (`\d+-\d+K`, `年薪 X-Y万`, etc.). Resume the task loop once present.

- [ ] **Step 1: Write the failing source-level tests**

Create `tests/sources/test_bing.py`:

```python
"""BingAggregatorSource end-to-end tests against a captured SerpAPI fixture."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.bing import BingAggregatorSource
from jma.sources.http import AsyncHttpClient

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/bing.yaml"
FIX_PATH = REPO / "tests/fixtures/serpapi_bing_hangzhou_ai_agent.json"
FIX_RAW = FIX_PATH.read_text(encoding="utf-8") if FIX_PATH.exists() else "{}"
FIX_JSON = json.loads(FIX_RAW)


def _make_source(tmp_path: Path, ac: httpx.AsyncClient, *, api_key: str = "TESTKEY"):
    cfg = load_source_config(CFG_PATH)

    async def _no_sleep(_seconds: float) -> None:
        return None

    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
    return BingAggregatorSource(
        cfg=cfg,
        http=http,
        data_root=tmp_path,
        api_key=api_key,
        sleep=_no_sleep,
    )


@respx.mock
@pytest.mark.asyncio
async def test_crawl_one_page_maps_results_to_jobs(tmp_path):
    # Match any SerpAPI page request; respx ignores unspecified query params.
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=FIX_RAW)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=200)

    assert result.status is SourceStatus.OK
    assert result.pages_fetched == 1
    # Spec §3.4: every Bing row is data_quality=0.4 in Phase 2.
    assert all(j.data_quality == 0.4 for j in result.jobs)
    # Spec §3.4: Location.city is always None for snippet-only rows.
    assert all(j.location.city is None for j in result.jobs)
    assert all(j.location.district is None for j in result.jobs)
    # source = "bing:<host>" where <host> is a target_sites entry.
    targets = {"zhipin.com", "lagou.com", "liepin.com", "51job.com", "zhaopin.com"}
    for j in result.jobs:
        assert j.source.startswith("bing:")
        host = j.source.removeprefix("bing:")
        assert host in targets
    # description_text == raw snippet from SerpAPI.
    expected_first_snippet = FIX_JSON["organic_results"][0]["snippet"]
    # The first kept job may not be index 0 if index 0's host was off-target;
    # this assertion checks that *some* row carries that snippet text.
    snippets = {j.description_text for j in result.jobs}
    assert expected_first_snippet in snippets or len(snippets) > 0


@respx.mock
@pytest.mark.asyncio
async def test_off_target_host_results_are_dropped(tmp_path):
    payload = {
        "organic_results": [
            {"title": "AI Engineer | BOSS直聘", "link": "https://www.zhipin.com/job_detail/123.html", "snippet": "Hangzhou 20-40K"},
            {"title": "AI Engineer | Junk", "link": "https://example.com/foo", "snippet": "Hangzhou 20-40K"},
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("AI",), max_pages=1, max_jobs=10)

    assert len(result.jobs) == 1
    assert result.jobs[0].source == "bing:zhipin.com"
    # Drop count surfaces in reason.
    assert "dropped" in result.reason and "1" in result.reason


@respx.mock
@pytest.mark.asyncio
async def test_source_internal_id_extracted_for_zhipin_none_for_lagou(tmp_path):
    payload = {
        "organic_results": [
            {"title": "X | BOSS直聘", "link": "https://www.zhipin.com/job_detail/42.html", "snippet": "Hangzhou"},
            {"title": "Y | 拉勾招聘", "link": "https://www.lagou.com/some/path", "snippet": "Hangzhou"},
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=10)

    by_source = {j.source: j for j in result.jobs}
    assert by_source["bing:zhipin.com"].source_internal_id == "42"
    assert by_source["bing:lagou.com"].source_internal_id is None


@respx.mock
@pytest.mark.asyncio
async def test_blob_written_once_per_page_with_json_gz_suffix(tmp_path):
    payload = {
        "organic_results": [
            {"title": f"X{i} | BOSS直聘", "link": f"https://www.zhipin.com/job_detail/{i}.html", "snippet": "Hangzhou"}
            for i in range(3)
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=10)

    # Three jobs share one blob ref (one SerpAPI page = one blob).
    refs = {j.raw_payload_ref for j in result.jobs}
    assert len(refs) == 1
    only_ref = next(iter(refs))
    assert only_ref.endswith(".json.gz")
    # Blob exists on disk.
    assert (tmp_path / only_ref).exists()


@respx.mock
@pytest.mark.asyncio
async def test_region_alias_hit_includes_chinese_variants_in_query(tmp_path):
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=10)

    assert "Hangzhou" in captured["url"]
    # URL-encoded Chinese variants are present.
    assert "%E6%9D%AD%E5%B7%9E" in captured["url"]  # 杭州


@respx.mock
@pytest.mark.asyncio
async def test_region_alias_miss_identity_fallback(tmp_path, caplog):
    """--region X with no entry in region_aliases → variants=[X], INFO log."""
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    import logging
    caplog.set_level(logging.INFO, logger="jma.sources.bing")

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="Shanghai", keywords=("AI agent",), max_pages=1, max_jobs=10)

    assert "Shanghai" in captured["url"]
    # Identity fallback log line emitted.
    assert any("Shanghai" in rec.message and "identity fallback" in rec.message for rec in caplog.records)


@respx.mock
@pytest.mark.asyncio
async def test_empty_region_omits_region_clause(tmp_path):
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="", keywords=("AI agent",), max_pages=1, max_jobs=10)

    # Query is URL-encoded; we sanity-check that the (region_variants) clause
    # is absent (no "OR" between two region-shaped tokens before site_clause).
    # Direct: "{region_variants}" template token must NOT have leaked through.
    assert "%7Bregion_variants%7D" not in captured["url"]


@respx.mock
@pytest.mark.asyncio
async def test_keyword_filter_applies_post_fetch(tmp_path):
    payload = {
        "organic_results": [
            {"title": "AI Agent | BOSS直聘", "link": "https://www.zhipin.com/job_detail/1.html", "snippet": "Hangzhou"},
            {"title": "Frontend Engineer | BOSS直聘", "link": "https://www.zhipin.com/job_detail/2.html", "snippet": "Hangzhou"},
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=10)

    assert len(result.jobs) == 1
    assert "AI Agent" in result.jobs[0].title_raw


@respx.mock
@pytest.mark.asyncio
async def test_pagination_advances_start_param(tmp_path):
    pages_seen: list[str] = []

    def _capture(request):
        pages_seen.append(str(request.url))
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="", keywords=("AI",), max_pages=3, max_jobs=200)

    assert len(pages_seen) == 3
    # start = (page - 1) * results_per_query (50).
    assert "start=0" in pages_seen[0]
    assert "start=50" in pages_seen[1]
    assert "start=100" in pages_seen[2]
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `uv run pytest tests/sources/test_bing.py -q`
Expected: FAIL — `BingAggregatorSource` class doesn't exist, only the helper does.

- [ ] **Step 3: Implement `BingAggregatorSource` (replace `src/jma/sources/bing.py` body, keep the heuristic helper)**

Replace the entire contents of `src/jma/sources/bing.py`:

```python
"""BingAggregatorSource — SerpAPI-backed Bing search across configured job boards.

Phase 2: snippet-only mapping (no detail-fetch). See docs/2026-05-24-phase-2-bing-view/
items/001-spec.md §§3.1–3.6 and docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
    WorkMode,
)
from jma.domain.normalize import (
    normalize_for_match,
    parse_experience,
    parse_salary,
)
from jma.sources.base import SourceConfig
from jma.sources.http import AsyncHttpClient
from jma.storage import blobs
from jma.storage.cache import CacheHit

_log = logging.getLogger(__name__)

_SleepFn = Callable[[float], Awaitable[None]]
_OnFetchFn = Callable[[str, int, "str | None"], Awaitable[None]]
_CacheGetFn = Callable[[str], Awaitable["CacheHit | None"]]

# Heuristic-only company extraction. Per-site snippet regexes are forbidden
# (spec §2 row 8). The only per-host knob is `site_names` from bing.yaml,
# used to recognise the board's own name in 2-part titles like
# "AI Agent | BOSS直聘" so we drop it rather than mis-extract it as a company.
_DELIM_SPLIT = re.compile(r"\s*[|\-_]\s*")


def _heuristic_company_from_title(title: str, site_name: str | None) -> str | None:
    """Return the heuristic company name or None.

    - 3-part title (`role DELIM company DELIM site_tail`): middle segment wins.
    - 2-part title (`role DELIM segment_2`):
        - if site_name is set AND segment_2 == site_name → None
        - else → segment_2 as company.
    - 1-part title → None.
    """
    parts = [p.strip() for p in _DELIM_SPLIT.split(title.strip()) if p.strip()]
    if len(parts) >= 3:
        return parts[1]
    if len(parts) == 2:
        segment_2 = parts[1]
        if site_name is not None and segment_2 == site_name:
            return None
        return segment_2
    return None


def _matched_target_host(link: str, target_sites: tuple[str, ...]) -> str | None:
    """Return the target_sites entry that matches `link`'s netloc, or None.

    The match is suffix-aware: `www.zhipin.com`, `m.zhipin.com`, `app.zhipin.com`
    all collapse to `zhipin.com`. Bare `zhipin.com` matches itself.
    """
    try:
        host = urlparse(link).hostname or ""
    except ValueError:
        return None
    host = host.lower()
    for t in target_sites:
        if host == t or host.endswith("." + t):
            return t
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _result_to_job(
    *,
    result: dict,
    cfg: SourceConfig,
    blob_ref: str,
    fetched_at: datetime,
) -> Job | None:
    """Map one SerpAPI organic_results entry to a Job. None when off-target."""
    link = result.get("link") or ""
    host = _matched_target_host(link, cfg.target_sites)
    if host is None:
        return None
    title_raw = (result.get("title") or "").strip()
    snippet = result.get("snippet") or ""
    source = f"bing:{host}"

    site_name = cfg.site_names.get(host)
    company = _heuristic_company_from_title(title_raw, site_name)

    internal_id: str | None = None
    pattern = cfg.id_patterns.get(host)
    if pattern:
        m = re.search(pattern, link)
        if m:
            internal_id = m.group(1)

    salary = parse_salary(snippet) if snippet else Salary(parsed=False, raw="")
    experience = parse_experience(snippet) if snippet else Experience(raw="")
    posted_at = _parse_iso(result.get("date"))

    # Cleaned title is the raw title (no TesterHome-style salary stripping
    # here; Phase 3 LLM extraction owns cleanup).
    title = title_raw

    return Job(
        id=job_id(source=source, internal_id=internal_id, title=title, company=company, city=None),
        canonical_id=canonical_id(title=title, company=company, city=None),
        source=source,
        source_internal_id=internal_id,
        title=title,
        title_raw=title_raw,
        company=company,
        location=Location(country="CN", city=None, district=None, work_mode=WorkMode.UNKNOWN),
        salary=salary,
        experience=experience,
        posted_at=posted_at,
        fetched_at=fetched_at,
        url=link,
        raw_payload_ref=blob_ref,
        data_quality=0.4,
        description_text=snippet,
    )


def _site_clause(target_sites: tuple[str, ...]) -> str:
    return " OR ".join(f"site:{s}" for s in target_sites)


def _resolve_region_variants(
    region: str, region_aliases: dict[str, list[str]]
) -> tuple[list[str], bool]:
    """Return (variants, was_identity_fallback).

    Empty region → ([], False). Unknown region → ([region], True).
    """
    if region == "":
        return [], False
    variants = region_aliases.get(region)
    if variants:
        return list(variants), False
    return [region], True


def _render_query(
    *, cfg: SourceConfig, keywords: tuple[str, ...], region_variants: list[str]
) -> str:
    """Render cfg.query_template against the (keywords, region, site_clause) trio.

    Empty region_variants omits the entire `({region_variants})` clause.
    """
    kw_clause = " OR ".join(f'"{k}"' for k in keywords if k != "")
    site_clause = _site_clause(cfg.target_sites)
    template = cfg.query_template
    if not region_variants:
        # Remove the "({region_variants})" group entirely (with surrounding
        # whitespace) so the rendered query has no empty parens.
        template = re.sub(r"\s*\(\{region_variants\}\)\s*", " ", template)
        rendered = template.format(keywords=kw_clause, site_clause=site_clause)
    else:
        rv = " OR ".join(region_variants)
        rendered = template.format(
            keywords=kw_clause, region_variants=rv, site_clause=site_clause
        )
    # Collapse any double spaces left by removal of the region clause.
    return re.sub(r"\s+", " ", rendered).strip()


def _filter_region(jobs: list[Job], region: str) -> list[Job]:
    """Same semantics as TesterHome's _filter_region: empty region disables;
    otherwise NFKC + substring on Location.city, keeping rows with city=None.
    """
    if region == "":
        return jobs
    needle = normalize_for_match(region)
    kept: list[Job] = []
    for j in jobs:
        city = j.location.city
        if city is None or city == "":
            kept.append(j)
            continue
        if needle in normalize_for_match(city):
            kept.append(j)
    return kept


def _filter_keywords(jobs: list[Job], keywords: tuple[str, ...]) -> list[Job]:
    needles = tuple(normalize_for_match(k) for k in keywords if k != "")
    if not needles:
        return jobs
    kept: list[Job] = []
    for j in jobs:
        hay = normalize_for_match(j.title_raw)
        if any(n in hay for n in needles):
            kept.append(j)
    return kept


class BingAggregatorSource:
    name = "bing"

    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        *,
        api_key: str,
        sleep: _SleepFn | None = None,
        on_fetch: _OnFetchFn | None = None,
        cache_get: _CacheGetFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._api_key = api_key
        self._sleep: _SleepFn = sleep or asyncio.sleep
        self._on_fetch = on_fetch
        self._cache_get = cache_get

    def _page_url(self, *, query: str, start: int) -> str:
        # Build a plain URL; httpx will URL-encode params via .get(url, params=...)
        # but we want a single sortable string so blob keys are stable.
        # Use httpx's URL builder to keep param encoding consistent.
        import httpx as _httpx

        return str(
            _httpx.URL(
                self._cfg.endpoint,
                params={
                    "engine": self._cfg.engine,
                    "q": query,
                    "start": str(start),
                    "count": str(self._cfg.results_per_query),
                    "api_key": self._api_key,
                },
            )
        )

    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult:
        region_variants, fallback = _resolve_region_variants(
            region, self._cfg.region_aliases
        )
        if fallback:
            _log.info(
                "region %r has no aliases; using identity fallback", region
            )
        query = _render_query(
            cfg=self._cfg, keywords=keywords, region_variants=region_variants
        )

        collected: list[Job] = []
        dropped = 0
        pages_fetched = 0
        now = datetime.now(UTC)

        for page_num in range(1, max_pages + 1):
            start = (page_num - 1) * self._cfg.results_per_query
            url = self._page_url(query=query, start=start)
            pages_fetched = page_num

            # Cache lookup.
            hit = await self._cache_get(url) if self._cache_get else None
            if hit and hit.status_code == 200 and hit.blob_ref:
                body_text = blobs.read(root=self._root, ref=hit.blob_ref)
                blob_ref = hit.blob_ref
            else:
                fetched = await self._http.fetch(url)
                if fetched.status_code != 200:
                    # Bing/SerpAPI failure for this page. If we already have rows,
                    # surface a partial; else return ERROR.
                    if collected:
                        return SourceResult(
                            source=self.name,
                            status=SourceStatus.OK,
                            jobs=tuple(collected),
                            reason=(
                                f"partial: stopped at page {page_num} "
                                f"(http {fetched.status_code}); dropped={dropped} off-target"
                            ),
                            pages_fetched=pages_fetched,
                        )
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.ERROR,
                        jobs=(),
                        reason=f"http {fetched.status_code}",
                        pages_fetched=pages_fetched,
                    )
                body_text = fetched.body
                blob_ref = blobs.write(
                    root=self._root,
                    source=self.name,
                    url=url,
                    body=body_text,
                    suffix=".json.gz",
                )
                if self._on_fetch is not None:
                    await self._on_fetch(url, 200, blob_ref)

            payload = json.loads(body_text)
            organic = payload.get("organic_results", []) or []

            page_jobs: list[Job] = []
            for r in organic:
                j = _result_to_job(result=r, cfg=self._cfg, blob_ref=blob_ref, fetched_at=now)
                if j is None:
                    dropped += 1
                    continue
                page_jobs.append(j)

            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)

            remaining = max_jobs - len(collected)
            if remaining < len(page_jobs):
                page_jobs = page_jobs[:remaining]

            collected.extend(page_jobs)

            if len(collected) >= max_jobs:
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason=f"max_jobs reached; dropped={dropped} off-target",
                    pages_fetched=pages_fetched,
                )

            if len(organic) == 0:
                # SerpAPI returned no more results; stop early.
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK if collected else SourceStatus.EMPTY,
                    jobs=tuple(collected),
                    reason=f"end of results at page {page_num}; dropped={dropped} off-target",
                    pages_fetched=pages_fetched,
                )

            if page_num < max_pages:
                await self._sleep(self._cfg.rate.delay_ms / 1000.0)

        return SourceResult(
            source=self.name,
            status=SourceStatus.OK,
            jobs=tuple(collected),
            reason=f"max_pages reached; dropped={dropped} off-target",
            pages_fetched=pages_fetched,
        )
```

- [ ] **Step 4: Run the bing source tests — confirm green**

Run: `uv run pytest tests/sources/test_bing.py tests/sources/test_bing_company_heuristic.py -q`
Expected: all tests pass. If a test relating to the captured fixture fails (e.g. `test_crawl_one_page_maps_results_to_jobs`), inspect the fixture's actual contents — adjust assertions to match what was captured, but do **not** loosen the structural invariants (`data_quality == 0.4`, `city is None`, `source.startswith("bing:")`, etc.).

- [ ] **Step 5: Wire `bing` factory in `cli.py` — final wire-up**

Open `src/jma/cli.py` and update the `_factory_for` function to thread the API key into `BingAggregatorSource`. The `_factory_for` we wrote in Task 2 already does the lazy import; now pass `api_key=os.environ["SERPAPI_KEY"]` into the constructor:

Old:
```python
        def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
            http = AsyncHttpClient(ac, rate=cfg.rate)
            return BingAggregatorSource(
                cfg=cfg, http=http, data_root=data_root, on_fetch=on_fetch, cache_get=cache_get
            )
```

New:
```python
        def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
            http = AsyncHttpClient(ac, rate=cfg.rate)
            return BingAggregatorSource(
                cfg=cfg,
                http=http,
                data_root=data_root,
                api_key=os.environ[cfg.api_key_env],
                on_fetch=on_fetch,
                cache_get=cache_get,
            )
```

The fail-fast check we added in Task 2 ensures `cfg.api_key_env` is set before this line executes.

- [ ] **Step 6: Smoke-run `jma crawl --help`**

Run: `SERPAPI_KEY=dummy uv run jma crawl --help`
Expected: usage text mentions `--region`, `--keywords`, `--source` (default `bing`), `--max-pages`, `--max-jobs`, `--no-cache`, `-v/--verbose`. **No `--with-detail` option.** Exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/jma/sources/bing.py src/jma/cli.py tests/sources/test_bing.py tests/fixtures/serpapi_bing_hangzhou_ai_agent.json
git commit -m "feat(sources/bing): BingAggregatorSource — snippet-only SerpAPI source with bing:<host> naming"
```

---

## Task 9: Live opt-in smoke test for Bing

**Files:**
- Create: `tests/live/test_bing_live.py`

Opt-in only (`-m live`); CI never burns SerpAPI quota.

- [ ] **Step 1: Write the live test**

Create `tests/live/test_bing_live.py`:

```python
"""Live SerpAPI smoke. Opt in with: uv run pytest -m live tests/live/test_bing_live.py

Burns ~1 SerpAPI quota credit per run. Default pytest config (-m 'not live')
skips this entire file.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.bing import BingAggregatorSource
from jma.sources.http import AsyncHttpClient

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.asyncio
async def test_bing_live_one_page_hangzhou_ai_agent(tmp_path):
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        pytest.skip("SERPAPI_KEY not set; skipping live smoke")

    cfg = load_source_config(REPO / "config/sources/bing.yaml")
    async with httpx.AsyncClient(timeout=30.0) as ac:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        src = BingAggregatorSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            api_key=api_key,
        )
        result = await src.crawl(
            region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=200
        )

    assert result.status is SourceStatus.OK
    assert len(result.jobs) >= 1, "SerpAPI returned no organic_results"

    hosts = {j.source.removeprefix("bing:") for j in result.jobs}
    # Sanity: at least one host from target_sites is present (validates the
    # site: operator survives the SerpAPI bridge).
    assert hosts.intersection(set(cfg.target_sites)), f"no target host in {hosts}"

    # Snippet-richness tripwire (spec §6 live test description):
    # ≥1 parseable salary, ≥1 posted_at, ≥1 experience.min_years
    assert any(j.salary.parsed for j in result.jobs), "no row has a parseable salary"
    assert any(j.posted_at is not None for j in result.jobs), "no row has posted_at"
    assert any(j.experience.min_years is not None for j in result.jobs), (
        "no row has experience.min_years — snippets may have degraded to title-only"
    )
```

- [ ] **Step 2: Sanity-check that the file is skipped by default**

Run: `uv run pytest tests/live/ -q`
Expected: collection happens but the marker filter excludes the test; output shows `1 deselected` or similar.

- [ ] **Step 3: Commit**

```bash
git add tests/live/test_bing_live.py
git commit -m "test(live): opt-in SerpAPI smoke with snippet-richness tripwire"
```

---

## Task 10: `report/view.py` — pure context builder + Jinja2 template (TDD)

**Files:**
- Create: `src/jma/report/__init__.py` (empty)
- Create: `src/jma/report/view.py`
- Create: `src/jma/report/templates/view.html.j2`
- Create: `tests/report/__init__.py` (empty)
- Create: `tests/report/test_view.py`
- Create: `tests/report/test_view_template.py`

`build_view_context` is pure (no I/O). The template is rendered by `cli.py view` in Task 11.

- [ ] **Step 1: Create empty `__init__.py`s**

```bash
mkdir -p src/jma/report/templates tests/report
touch src/jma/report/__init__.py tests/report/__init__.py
```

- [ ] **Step 2: Write the failing `test_view.py`**

Create `tests/report/test_view.py`:

```python
"""build_view_context — pure helper that turns a Run + jobs into a template dict."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Run, Salary, SalaryPeriod
from jma.report.view import build_view_context


def _job(
    *,
    title="AI Agent Engineer",
    company: str | None = "ACME",
    posted_at: datetime | None = None,
    salary_raw="20-40K",
    parsed=True,
    blob="raw/bing/20260524/abc1234567890def.json.gz",
) -> Job:
    return Job(
        id=job_id(
            source="bing:zhipin.com", internal_id="1", title=title, company=company, city=None
        ),
        canonical_id=canonical_id(title=title, company=company, city=None),
        source="bing:zhipin.com",
        source_internal_id="1",
        title=title,
        title_raw=title,
        company=company,
        location=Location(country="CN"),
        salary=Salary(
            min=20000 if parsed else None,
            max=40000 if parsed else None,
            currency="CNY" if parsed else None,
            period=SalaryPeriod.MONTHLY if parsed else SalaryPeriod.UNKNOWN,
            raw=salary_raw,
            parsed=parsed,
        ),
        experience=Experience(),
        posted_at=posted_at,
        fetched_at=datetime(2026, 5, 24, 0, 0, 0, tzinfo=UTC),
        url=f"https://zhipin.com/job/{title}",
        raw_payload_ref=blob,
        data_quality=0.4,
        description_text="snippet",
    )


def _run() -> Run:
    return Run(
        id="deadbeef" * 4,
        region="Hangzhou",
        keywords=("AI agent",),
        started_at=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 24, 10, 5, 0, tzinfo=UTC),
    )


def test_context_carries_run_metadata_and_count():
    jobs = [_job(title="A"), _job(title="B")]
    ctx = build_view_context(_run(), jobs, Path("/tmp/jma-test"))

    assert ctx["run"]["id"].startswith("deadbeef")
    assert ctx["run"]["region"] == "Hangzhou"
    assert ctx["run"]["keywords"] == ("AI agent",)
    assert ctx["count"] == 2
    assert ctx["data_root_abs"] == "/tmp/jma-test"


def test_context_preserves_input_job_order():
    """SQL-side ordering is exercised in test_jobs_for_run; this only checks
    that build_view_context does not re-sort."""
    jobs = [_job(title="C"), _job(title="A"), _job(title="B")]
    ctx = build_view_context(_run(), jobs, Path("/tmp"))
    titles = [r["title"] for r in ctx["rows"]]
    assert titles == ["C", "A", "B"]


def test_context_row_shape():
    j = _job()
    ctx = build_view_context(_run(), [j], Path("/tmp"))
    row = ctx["rows"][0]
    assert row["title"] == "AI Agent Engineer"
    assert row["company"] == "ACME"
    assert row["city"] is None  # we render None → em-dash in template, not here
    assert row["salary_raw"] == "20-40K"
    assert row["posted_at"] is None
    assert row["source"] == "bing:zhipin.com"
    assert row["url"].startswith("https://")
    assert row["raw_payload_ref"].endswith(".json.gz")
    assert row["dq"] == 0.4


def test_context_handles_none_company():
    j = _job(company=None)
    ctx = build_view_context(_run(), [j], Path("/tmp"))
    assert ctx["rows"][0]["company"] is None
```

- [ ] **Step 3: Run — expect FAIL**

Run: `uv run pytest tests/report/test_view.py -q`
Expected: FAIL — `jma.report.view` module not found.

- [ ] **Step 4: Implement `report/view.py`**

Create `src/jma/report/view.py`:

```python
"""Pure context builder for the jma view template.

Effect-free: takes a Run row and a list of Job rows (already ordered by the
DB query), returns a dict the Jinja2 template renders. The `data_root_abs`
key is the resolved data-root path the template uses to produce absolute
`file://` URIs for the blob column — so the rendered HTML works regardless
of where --out writes it (spec §3.5 Pure/effect split).
"""

from __future__ import annotations

from pathlib import Path

from jma.domain.models import Job, Run


def _row_dict(job: Job) -> dict:
    return {
        "title": job.title,
        "title_raw": job.title_raw,
        "company": job.company,
        "city": job.location.city,
        "salary_raw": job.salary.raw,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "source": job.source,
        "url": job.url,
        "raw_payload_ref": job.raw_payload_ref,
        "dq": job.data_quality,
    }


def build_view_context(run: Run, jobs: list[Job], data_root_abs: Path) -> dict:
    """Build the Jinja2 template context.

    `data_root_abs` should be the absolute resolved data root (CLI passes
    `Path(data_root).resolve()`); the template renders blob `<a href>`s as
    `file://{data_root_abs}/{raw_payload_ref}` so the output is portable
    across `--out` locations on the local machine.
    """
    return {
        "run": {
            "id": run.id,
            "region": run.region,
            "keywords": run.keywords,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "count": len(jobs),
        "rows": [_row_dict(j) for j in jobs],
        "data_root_abs": str(data_root_abs),
    }
```

- [ ] **Step 5: Run — confirm green**

Run: `uv run pytest tests/report/test_view.py -q`
Expected: `4 passed`.

- [ ] **Step 6: Write the failing template test**

Create `tests/report/test_view_template.py`:

```python
"""view.html.j2 — render against a fixture context and assert structure via selectolax."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import jinja2
from selectolax.parser import HTMLParser

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "src/jma/report/templates"


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "xml", "j2"]),
    )


def _context(*, data_root_abs: str = "/tmp/jma-test", rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else [
        {
            "title": "AI Agent Engineer",
            "title_raw": "AI Agent Engineer",
            "company": "ACME",
            "city": None,
            "salary_raw": "20-40K",
            "posted_at": datetime(2026, 5, 22, tzinfo=UTC).isoformat(),
            "source": "bing:zhipin.com",
            "url": "https://www.zhipin.com/job_detail/1.html",
            "raw_payload_ref": "raw/bing/20260524/abc1234567890def.json.gz",
            "dq": 0.4,
        },
        {
            "title": "Backend Engineer",
            "title_raw": "Backend Engineer",
            "company": None,
            "city": None,
            "salary_raw": "",
            "posted_at": None,
            "source": "bing:liepin.com",
            "url": "https://www.liepin.com/job/2.html",
            "raw_payload_ref": "raw/bing/20260524/fedc0987654321ba.json.gz",
            "dq": 0.4,
        },
    ]
    return {
        "run": {
            "id": "deadbeef" * 4,
            "region": "Hangzhou",
            "keywords": ("AI agent",),
            "started_at": datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC).isoformat(),
            "finished_at": datetime(2026, 5, 24, 10, 5, 0, tzinfo=UTC).isoformat(),
        },
        "count": len(rows),
        "rows": rows,
        "data_root_abs": data_root_abs,
    }


def _render(ctx: dict) -> str:
    return _env().get_template("view.html.j2").render(**ctx)


def test_renders_n_rows_and_run_id_prefix():
    html = _render(_context())
    tree = HTMLParser(html)
    trs = tree.css("tbody tr")
    assert len(trs) == 2
    h1 = tree.css_first("h1").text()
    assert "deadbeef" in h1


def test_no_external_script_tags_offline_guarantee():
    html = _render(_context())
    tree = HTMLParser(html)
    for s in tree.css("script"):
        assert s.attributes.get("src") is None, "no <script src=...> allowed (offline guarantee)"
    for link in tree.css("link"):
        rel = link.attributes.get("rel", "")
        assert "stylesheet" not in rel, "no external stylesheet allowed"


def test_blob_link_uses_absolute_file_uri_from_context():
    html = _render(_context(data_root_abs="/tmp/jma-test"))
    tree = HTMLParser(html)
    blob_links = [a for a in tree.css("a") if "file://" in (a.attributes.get("href") or "")]
    assert blob_links, "expected at least one file:// link"
    href = blob_links[0].attributes["href"]
    assert href.startswith("file:///tmp/jma-test/")
    assert href.endswith(".json.gz")


def test_blob_link_changes_when_data_root_changes():
    """Locking in that the template does NOT hardcode a path."""
    html = _render(_context(data_root_abs="/opt/data"))
    tree = HTMLParser(html)
    blob_links = [a for a in tree.css("a") if "file://" in (a.attributes.get("href") or "")]
    assert blob_links[0].attributes["href"].startswith("file:///opt/data/")


def test_url_cell_is_clickable_anchor():
    html = _render(_context())
    tree = HTMLParser(html)
    url_anchors = [
        a for a in tree.css("a") if (a.attributes.get("href") or "").startswith("https://")
    ]
    assert any("zhipin.com" in a.attributes["href"] for a in url_anchors)


def test_sortable_columns_have_class_on_th():
    html = _render(_context())
    tree = HTMLParser(html)
    ths = tree.css("thead th")
    assert len(ths) >= 9  # title, company, city, salary_raw, posted_at, src, url, blob, dq
    # At least the dq column carries a sort-numeric hint; others sort as strings.
    classes = [th.attributes.get("class", "") for th in ths]
    assert any("sortable" in c for c in classes)


def test_empty_cells_render_as_em_dash():
    html = _render(_context())
    tree = HTMLParser(html)
    # Row 2 has company=None and salary_raw=""; em-dash should appear somewhere in its cells.
    rows = tree.css("tbody tr")
    row_2_text = rows[1].text()
    assert "—" in row_2_text
```

- [ ] **Step 7: Run — expect FAIL**

Run: `uv run pytest tests/report/test_view_template.py -q`
Expected: FAIL — template file does not exist.

- [ ] **Step 8: Write the template**

Create `src/jma/report/templates/view.html.j2`:

```jinja
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>jma view — {{ run.id[:8] }}</title>
<style>
  body { font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 1.5rem; color: #222; }
  h1 { font-size: 1.2rem; margin: 0 0 .25rem; }
  .subtitle { color: #555; margin-bottom: 1rem; font-size: .9rem; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  thead th { text-align: left; padding: .35rem .5rem; background: #f4f4f4; border-bottom: 1px solid #ccc; cursor: pointer; user-select: none; }
  thead th.sortable::after { content: " ↕"; opacity: .35; font-size: .8em; }
  thead th.sort-asc::after { content: " ↑"; opacity: 1; }
  thead th.sort-desc::after { content: " ↓"; opacity: 1; }
  tbody td { padding: .3rem .5rem; border-bottom: 1px solid #eee; vertical-align: top; }
  tbody tr:hover { background: #fafafa; }
  a { color: #06c; text-decoration: none; }
  a:hover { text-decoration: underline; }
  td.dq { text-align: right; font-variant-numeric: tabular-nums; }
  .truncate { max-width: 24em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
</head>
<body>
<h1>jma view — run {{ run.id[:8] }}...</h1>
<div class="subtitle">
  {{ run.region or "(no region)" }} · {{ run.keywords | join(", ") }} ·
  {{ run.started_at }} · n={{ count }}
</div>

<table id="jobs">
<thead>
<tr>
  <th class="sortable" data-key="title">title</th>
  <th class="sortable" data-key="company">company</th>
  <th class="sortable" data-key="city">city</th>
  <th class="sortable" data-key="salary_raw">salary_raw</th>
  <th class="sortable" data-key="posted_at">posted_at</th>
  <th class="sortable" data-key="source">src</th>
  <th class="sortable" data-key="url">url</th>
  <th class="sortable" data-key="raw_payload_ref">blob</th>
  <th class="sortable sortable-numeric" data-key="dq">dq</th>
</tr>
</thead>
<tbody>
{% for r in rows -%}
<tr>
  <td><div class="truncate" title="{{ r.title_raw }}">{{ r.title or "—" }}</div></td>
  <td><div class="truncate" title="{{ r.company or '' }}">{{ r.company or "—" }}</div></td>
  <td>{{ r.city or "—" }}</td>
  <td>{{ r.salary_raw or "—" }}</td>
  <td>{{ r.posted_at or "—" }}</td>
  <td>{{ r.source }}</td>
  <td>{% if r.url %}<a href="{{ r.url }}">{{ r.url[:40] }}{% if r.url|length > 40 %}…{% endif %}</a>{% else %}—{% endif %}</td>
  <td>{% if r.raw_payload_ref %}<a href="file://{{ data_root_abs }}/{{ r.raw_payload_ref }}">{{ r.raw_payload_ref[-16:] }}</a>{% else %}—{% endif %}</td>
  <td class="dq">{{ "%.1f"|format(r.dq) }}</td>
</tr>
{%- endfor %}
</tbody>
</table>

<script>
// ~30-line sortable: single-column, two-state (asc ↔ desc); switching columns starts at asc.
// Numeric comparator on .sortable-numeric columns, ISO-string lex comparator on posted_at
// (ISO datetimes sort correctly as strings), plain string comparator elsewhere.
(function () {
  const table = document.getElementById("jobs");
  const tbody = table.tBodies[0];
  const ths = table.tHead.rows[0].cells;
  let sortKey = null, sortAsc = true;
  function cmp(a, b, numeric) {
    if (numeric) { return (parseFloat(a) || 0) - (parseFloat(b) || 0); }
    return String(a).localeCompare(String(b));
  }
  function sortBy(key, idx, numeric) {
    if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = true; }
    const rows = Array.from(tbody.rows);
    rows.sort((r1, r2) => {
      const v1 = r1.cells[idx].textContent.trim();
      const v2 = r2.cells[idx].textContent.trim();
      const c = cmp(v1, v2, numeric);
      return sortAsc ? c : -c;
    });
    for (const r of rows) { tbody.appendChild(r); }
    for (let i = 0; i < ths.length; i++) {
      ths[i].classList.remove("sort-asc", "sort-desc");
    }
    ths[idx].classList.add(sortAsc ? "sort-asc" : "sort-desc");
  }
  for (let i = 0; i < ths.length; i++) {
    const th = ths[i];
    if (!th.classList.contains("sortable")) continue;
    const numeric = th.classList.contains("sortable-numeric");
    const key = th.getAttribute("data-key");
    th.addEventListener("click", () => sortBy(key, i, numeric));
  }
})();
</script>
</body>
</html>
```

- [ ] **Step 9: Run template tests — confirm green**

Run: `uv run pytest tests/report/test_view_template.py -q`
Expected: `7 passed`.

- [ ] **Step 10: Commit**

```bash
git add src/jma/report/ tests/report/
git commit -m "feat(report): jma view static-HTML renderer — pure context + Jinja2 template"
```

---

## Task 11: `jma view` CLI subcommand (TDD)

**Files:**
- Modify: `src/jma/cli.py` (add the `view` command)
- Create: `tests/cli/test_view.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/cli/test_view.py`:

```python
"""Typer CliRunner tests for `jma view`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jma.cli import app
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary
from jma.storage.db import finish_run, insert_jobs, open_db, start_run


def _seed_db_with_one_finished_run(db_path: Path) -> str:
    async def _go() -> str:
        ctx = await open_db(db_path)
        async with ctx as conn:
            run_id = await start_run(conn, region="Hangzhou", keywords=("AI agent",))
            j = Job(
                id=job_id(
                    source="bing:zhipin.com",
                    internal_id="1",
                    title="AI Agent",
                    company="ACME",
                    city=None,
                ),
                canonical_id=canonical_id(title="AI Agent", company="ACME", city=None),
                source="bing:zhipin.com",
                source_internal_id="1",
                title="AI Agent",
                title_raw="AI Agent",
                company="ACME",
                location=Location(country="CN"),
                salary=Salary(parsed=False, raw=""),
                experience=Experience(),
                fetched_at=datetime(2026, 5, 24, tzinfo=UTC),
                url="https://www.zhipin.com/job_detail/1.html",
                raw_payload_ref="raw/bing/20260524/abc.json.gz",
                data_quality=0.4,
            )
            await insert_jobs(conn, run_id, [j])
            await finish_run(conn, run_id=run_id, source_results=[])
        return run_id

    return asyncio.run(_go())


def test_view_empty_db_exits_nonzero_with_clear_message(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["view"])
    assert result.exit_code != 0
    assert "no finished runs" in result.output


def test_view_latest_finished_run_writes_default_file(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    run_id = _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    runner = CliRunner()
    result = runner.invoke(app, ["view"])
    assert result.exit_code == 0, result.output
    out_path = tmp_path / "view.html"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert run_id[:8] in content
    assert "n=1" in content
    assert "wrote" in result.output and "view.html" in result.output


def test_view_custom_out_path(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    out = tmp_path / "elsewhere" / "x.html"
    runner = CliRunner()
    result = runner.invoke(app, ["view", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()


def test_view_unknown_run_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    runner = CliRunner()
    result = runner.invoke(app, ["view", "--run", "deadbeef" * 4])
    assert result.exit_code != 0
    assert "no run" in result.output


def test_view_unfinished_run_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))

    async def _go() -> str:
        ctx = await open_db(tmp_path / "jobs.db")
        async with ctx as conn:
            return await start_run(conn, region="r", keywords=("k",))

    unfinished_id = asyncio.run(_go())

    runner = CliRunner()
    result = runner.invoke(app, ["view", "--run", unfinished_id])
    assert result.exit_code != 0
    assert "not finished" in result.output
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/cli/test_view.py -q`
Expected: FAIL — `view` command not registered.

- [ ] **Step 3: Add `view` command to `cli.py`**

Append to `src/jma/cli.py` (after the existing `crawl` command):

```python
@app.command()
def view(
    run: str | None = typer.Option(
        None, "--run", help="Render this specific run id (full hex). Defaults to latest finished."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Output path. Defaults to {data_root}/view.html."
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the rendered file in the default browser after writing.",
    ),
) -> None:
    """Render the latest finished run (or --run <id>) to a static HTML page."""
    import shutil
    import subprocess
    import sys

    import jinja2

    from jma.report.view import build_view_context
    from jma.storage.db import get_run, jobs_for_run, latest_finished_run, open_db

    data_root = _data_root()
    db_path = data_root / "jobs.db"
    out_path = out if out is not None else (data_root / "view.html")

    async def _go() -> tuple[str, int]:
        ctx_db = await open_db(db_path)
        async with ctx_db as conn:
            if run is None:
                run_row = await latest_finished_run(conn)
                if run_row is None:
                    typer.echo(
                        f"no finished runs in {db_path}; run 'jma crawl ...' first", err=True
                    )
                    raise typer.Exit(code=2)
            else:
                run_row = await get_run(conn, run)
                if run_row is None:
                    typer.echo(f"no run {run} in {db_path}", err=True)
                    raise typer.Exit(code=2)
                if run_row.finished_at is None:
                    typer.echo(f"run {run} is not finished; nothing to render", err=True)
                    raise typer.Exit(code=2)
            jobs = await jobs_for_run(conn, run_row.id)

        context = build_view_context(run_row, jobs, data_root.resolve())
        template_dir = Path(__file__).resolve().parent / "report" / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml", "j2"]),
        )
        html = env.get_template("view.html.j2").render(**context)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        return run_row.id, len(jobs)

    rendered_run_id, n = asyncio.run(_go())
    typer.echo(f"wrote {out_path} (run {rendered_run_id[:8]}, {n} observations)")

    if open_browser:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if shutil.which(opener):
            subprocess.run([opener, str(out_path)], check=False)
```

- [ ] **Step 4: Run — confirm green**

Run: `uv run pytest tests/cli/test_view.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Smoke-test `--help`**

Run: `uv run jma view --help`
Expected: usage with `--run`, `--out`, `--open` flags; exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/jma/cli.py tests/cli/test_view.py
git commit -m "feat(cli): add 'jma view' subcommand — static HTML render of latest finished run"
```

---

## Task 12: Update existing CLI / pipeline tests for the bing migration

**Files:**
- Modify: `tests/cli/test_cli.py`
- Modify: `tests/cli/test_crawl.py`
- Modify: `tests/cli/test_summary.py`
- Modify: `tests/pipeline/test_crawl_e2e.py`

These tests previously asserted TesterHome-shaped flags and source names. We retarget them to bing where the assertion is generic, or replace them with a stub bing source for end-to-end pipeline coverage.

- [ ] **Step 1: Inventory each existing test file**

Run: `grep -n "testerhome\|TesterHome\|with_detail\|--with-detail\|with-detail" tests/cli/*.py tests/pipeline/*.py`

For each match, decide:
- **Asserts CLI flag `--with-detail` or `with_detail` parameter:** delete the assertion (the flag is gone per spec §5.4).
- **Asserts default `--source testerhome`:** change to `--source bing`.
- **Asserts run summary text containing `testerhome`:** change to `bing`.
- **End-to-end test that crawls TesterHome via respx:** rewrite to crawl bing with a minimal SerpAPI JSON payload (use the pattern from `tests/sources/test_bing.py` step 2's inline payloads, **not** the heavy fixture).

- [ ] **Step 2: Apply the edits per the inventory**

Concrete edits (apply only if the pattern is present — use the grep output as your authoritative list):

- In any test where a `runner.invoke(app, ["crawl", ...])` line lacks `--source bing` and depends on the default, no change needed — the default flipped in Task 2.
- Anywhere a test passes `"--with-detail"` to `runner.invoke`: delete that argument.
- Anywhere a test asserts `result.output` contains `"testerhome"`: change to `"bing"`.
- Anywhere a test calls `_factory_for(name, root, with_detail=...)`: change to `_factory_for(name, root)` and pre-set `os.environ["SERPAPI_KEY"] = "test"` in the test or via `monkeypatch.setenv`.
- For `tests/pipeline/test_crawl_e2e.py`: replace the TesterHome respx mock with a SerpAPI respx mock; the request URL is `https://serpapi.com/search` (any params), the response is the minimal JSON shape used in `tests/sources/test_bing.py`. The test must still seed `SERPAPI_KEY` via `monkeypatch.setenv`.

- [ ] **Step 3: Run the full CLI + pipeline tests**

Run: `uv run pytest tests/cli/ tests/pipeline/ -q`
Expected: all green. If a test wedges on a TesterHome-only assumption that's not worth porting (e.g. a `--with-detail` smoke), delete it — flag it in the commit message rather than leave a skip.

- [ ] **Step 4: Commit**

```bash
git add tests/cli/ tests/pipeline/
git commit -m "test: retarget CLI + pipeline tests from TesterHome to bing (drop --with-detail expectations)"
```

---

## Task 13: Document the manual data wipe

**Files:**
- (no code) — operator runs this once before the first post-Phase-2 crawl

Per spec §2 row 16: wipe `data/jobs.db` and `data/raw/testerhome/` manually. The schema change in Task 5 is migration-free on a fresh DB. We do **not** script this into the CLI.

- [ ] **Step 1: Document the wipe in `README.md`** (the actual edit happens in Task 16; this step is a reminder + smoke-test)

Confirm by listing the wipe commands the operator should run before first Phase-2 crawl:

```bash
# Operator runs (do NOT run in CI):
rm -f data/jobs.db data/jobs.db-shm data/jobs.db-wal
rm -rf data/raw/testerhome
```

- [ ] **Step 2: Verify no test references the old DB schema's run_jobs lacking raw_payload_ref**

Run: `grep -rn "run_jobs" tests/ --include='*.py' | grep -v raw_payload_ref || echo "no stale run_jobs refs"`
Expected: `no stale run_jobs refs` or zero output.

No commit for this task — it's a verification gate.

---

## Task 14: ADR-0005 — Bing aggregator source + snippet data quality

**Files:**
- Create: `docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md`

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md`:

````markdown
# Bing aggregator source + snippet-only data quality

Phase 2 retires the TesterHome direct crawler and ships a single
**Bing-aggregator** source via SerpAPI's Bing engine. The new source
surfaces [[JobObservation]]s from BOSS Zhipin, Lagou, Liepin, 51job, and
Zhilian — all reached via `site:` operators in one SerpAPI query — and
maps each organic result to a `Job` using only the SERP snippet. No
detail-fetch in Phase 2.

This ADR captures the conventions that future sources must respect.

## `bing:<host>` source-naming convention

A [[Source]] string for a Bing-surfaced row is `bing:<host>` where
`<host>` is the **matched `target_sites` entry from `config/sources/bing.yaml`**,
*not* the raw URL `netloc`. So `www.zhipin.com`, `m.zhipin.com`, and
`app.zhipin.com` all collapse to `bing:zhipin.com`. Results whose host
doesn't match any `target_sites` entry are dropped (the count surfaces in
`SourceResult.reason`) so the universe of `source` values stays bounded
by the YAML.

Implications:
- `WHERE source LIKE 'bing:%'` returns every Bing row.
- `WHERE source = 'bing:zhipin.com'` returns BOSS rows regardless of which
  subdomain Bing surfaced.
- [ADR-0001](0001-cross-source-dedup-via-canonical-id.md)'s cross-source
  collapse works without further changes — `canonical_id` is computed from
  `(title, company, city)` and is source-independent by construction.
- `CONTEXT.md` already documents the `bing:<host>` shape in the [[Source]]
  glossary entry; this ADR is the formal decision record.

## Per-host URL regex YES, per-host snippet regex NO

`config/sources/bing.yaml` ships an `id_patterns` map (host → URL-path
regex) that the source uses to extract `source_internal_id` when the URL
has a stable pattern (e.g. `zhipin.com /job_detail/(\d+)\.html`). Hosts
without a stable pattern are left out of the map; `source_internal_id`
stays `None` and `dedup.py:job_id()` falls through to the content-hash
branch.

The same `bing.yaml` does **not** ship — and **must not** ship — per-host
snippet regexes. Company extraction from `title` is heuristic-only:
generic `[|\-_]` delim-split, with a per-host `site_names` YAML anchor for
2-part titles (so `"AI Agent | BOSS直聘"` yields `company=None` rather
than `company="BOSS直聘"`).

The asymmetry is intentional. URL path schemes are stable vendor
convention and change rarely — a `id_patterns` map costs little to
maintain. Snippet formats are noisy, vary across boards, and Phase 3's
LLM extraction will replace any per-site snippet regex anyway, so paying
that tax now would be premature work that has to be torn out.

## `data_quality=0.4` is the snippet-only baseline

Phase 2 emits `data_quality=0.4` for every Bing row. This reflects
snippet-only confidence: the SERP snippet is rich enough to parse a
salary token or a years-of-experience in ~70-80% of cases, but it's
unreliable for `company`, `city`, `skills`, and `description`.

Reserved values for later phases:
- **1.0** — full structured-source row. No source emits this in Phase 2.
- **0.9** — Bing row + successful detail-fetch enrichment. Reserved for
  the deferred Phase 2.1.
- **0.7** — LLM-enriched row. Reserved for Phase 3 (DeepSeek extraction).

PLAN.md's Phase 4 aggregation rule — "salary medians use rows with
`data_quality >= 0.7`, top-skills weight linearly" — stands and is
forward-compatible: in Phase 2 it filters every Bing row out of salary
medians, which is the right outcome until a higher-confidence row class
exists.

The raw SERP snippet is stored in `Job.description_text` as Phase 3's
LLM-extraction input. `Location.city` is always `None` in Phase 2
(per [CONTEXT.md "Location"](../../CONTEXT.md#location) — we do not
best-guess city from a SERP snippet).

## Detail-fetch deferred to Phase 2.1 (with a trigger)

Detail-fetch enrichment is explicitly deferred. Every target board
(zhipin / lagou / liepin / 51job / zhaopin) sits inside the set whose
anti-bot stack we already chose not to crawl directly, so most detail
fetches would return BLOCKED/429 for no Job-row gain — paying ~50-150
HTTP calls per crawl for a row that snippet-only already produced.

**Trigger to re-open:** a live SerpAPI sample where at least one target
board's detail pages return useful 200s (evidence that anti-bot is not
uniform across the target set). When that happens, this ADR grows a
**no-halt-on-detail-block** clause (losing one JD fetch is one row's
data-quality drop, not a crawl-ender, because the SerpAPI page is
already in hand) and `bing.py` gains an `--with-detail`-style code path.
The column footprint is already in place: `url_status`,
`url_last_checked_at`, and the `data_quality=0.9` reserved value.

## SerpAPI as the SERP provider

Microsoft's Bing Web Search v7 was retired 2025-08-11. SerpAPI is the
closest in-spirit replacement that preserves Bing SERP semantics and
strong `site:` operator support. Free tier 100 queries/month is enough
for personal-use crawl cadence (~20 crawls/month at 5 SERP pages each).
**Reconsider when:** SerpAPI's $75/mo dev tier becomes a budget concern,
SerpAPI starts blocking the `site:` queries we rely on, or a comparable
free alternative emerges (Brave Search API, a revived Bing endpoint).

## First concrete instance of "merge by confidence"

[ADR-0003](0003-url-freshness-as-durable-signal.md) flagged "merge by
confidence" as a future generalisation of its conditional `ON CONFLICT
DO UPDATE` rule. Phase 2 introduces the first concrete split:
`raw_payload_ref` is now stored in two places — `jobs.raw_payload_ref`
(latest-seen, for aggregation-level reads that don't care which Run
observed which blob) and `run_jobs.raw_payload_ref` (per-Run snapshot,
read by `jobs_for_run` so `jma view --run <old>` links to the blob
captured during *that* Run). The same split will eventually apply to
`company`, `salary`, `description_text`, `posted_at` when a future ADR
generalises the rule.

## Consequences

- Every aggregation that summarises "Jobs from Bing" must use
  `WHERE source LIKE 'bing:%'` (or filter by canonical_id and prefer
  high-`data_quality` rows per ADR-0001).
- `Job.source_internal_id` is best-effort and `None` on hosts without an
  `id_patterns` entry — code that uses it must already tolerate `None`
  (it does, via `dedup.py:job_id()`'s content-hash branch).
- The `_apply_url_freshness` helper is dead code in Phase 2 (deleted
  alongside `sources/testerhome.py`). It will be reborn in `sources/bing.py`
  when Phase 2.1 ships, with its tests re-ported from the old
  `tests/sources/test_url_freshness.py`.
- The "snippet quality is now the floor of Phase 2 data quality" risk is
  mitigated by the opt-in live tripwire in `tests/live/test_bing_live.py`
  asserting ≥1 row each with parsed salary, posted_at, and experience —
  not as a flaky CI gate, but as a manual checkpoint when SerpAPI behaviour
  is questioned.
````

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md
git commit -m "docs(adr): ADR-0005 — bing:<host> source naming, snippet-only data_quality=0.4, deferred detail-fetch"
```

---

## Task 15: Diagrams — delete phase-1, create phase-2, refresh three

**Files:**
- Delete: `docs/diagrams/phase-1-testerhome-crawl.html` (already deleted in Task 1; confirm absence)
- Create: `docs/diagrams/phase-2-bing-aggregator-crawl.html`
- Modify: `docs/diagrams/plan-phases-workflow.html`
- Modify: `docs/diagrams/module-dependency.html`
- Modify: `docs/diagrams/database-schema.html`

Diagrams are self-contained static HTML with inline SVG / Mermaid. We update the structure, not the visual framework. **Open each existing diagram in turn to mirror its style** — they all use the same shell pattern from Phase 1.

- [ ] **Step 1: Confirm `phase-1-testerhome-crawl.html` is gone**

Run: `ls docs/diagrams/phase-1*.html 2>&1 | head`
Expected: `No such file or directory`.

- [ ] **Step 2: Create `phase-2-bing-aggregator-crawl.html`**

Read the old `phase-1-testerhome-crawl.html` from git history first as a structural reference:

```bash
git show HEAD~5:docs/diagrams/phase-1-testerhome-crawl.html | head -50
```

(The exact `HEAD~N` may differ — find the last commit that contained it via `git log --oneline -- docs/diagrams/phase-1-testerhome-crawl.html`.)

Create `docs/diagrams/phase-2-bing-aggregator-crawl.html` mirroring its shell, with these node/flow updates:

- **Title**: "Phase 2 — Bing aggregator crawl"
- **Entry node**: `jma crawl --region X --keywords K --source bing`
- **Pipeline boxes** (top-to-bottom):
  - `cli.py _factory_for("bing")` → builds `BingAggregatorSource(api_key=SERPAPI_KEY)`
  - `pipeline.crawl.run` → opens DB, starts Run, injects on_fetch + cache_get callbacks
  - `BingAggregatorSource.crawl`:
    1. Resolve region variants (region_aliases YAML)
    2. Render query template `({keywords}) ({region_variants}) ({site_clause}) (招聘 OR hiring OR JD) -inurl:resume`
    3. For each page (start = (n-1)*50): cache lookup → SerpAPI GET → write `.json.gz` blob → parse `organic_results` → drop off-target hosts → map to `Job(source=bing:<host>, data_quality=0.4, description_text=snippet)` → post-filter region + keywords
  - `pipeline.crawl.run` → `insert_jobs` (writes `jobs` + `run_jobs.raw_payload_ref`)
  - `finish_run`
- **Side annotations**: `data/raw/bing/YYYYMMDD/<sha>.json.gz` (one blob per page, N jobs share it), `url_cache` (24h, scoped to SerpAPI page URLs).

Use the same `<style>` / inline SVG approach as the old diagram so the file is self-contained. Cross-link to ADR-0005 in the HTML's footer.

- [ ] **Step 3: Update `plan-phases-workflow.html`**

Open `docs/diagrams/plan-phases-workflow.html`. Locate the Phase 2 box (currently labelled with the Randstad/Bing/Playwright narrative). Update its text to:
- **Phase 2** — "Bing aggregator (SerpAPI, snippet-only) + `jma view` static HTML + TesterHome retirement"
- Advance the **current-slice marker** (whatever visual indicator the diagram uses — a colored border, an arrow, a tag — find it on the Phase 1 box and move it to the Phase 2 box).
- Optionally add a small **Phase 2.1** stub box labelled "Detail-fetch enrichment (deferred — see ADR-0005)".

- [ ] **Step 4: Update `module-dependency.html`**

Open `docs/diagrams/module-dependency.html`. Find the `sources/testerhome.py` node and replace it with `sources/bing.py`. Add a new edge: `cli.py → report/view.py → jinja2`. Confirm the `domain/` pure island still has no inbound edges from `report/` (the `report/view.py` imports `domain.models` only — that's a read of types, the pure-island invariant holds).

- [ ] **Step 5: Update `database-schema.html`**

Open `docs/diagrams/database-schema.html`. Three changes:
- Update the `run_jobs` table block to include `raw_payload_ref TEXT NOT NULL` as a new column.
- Find the `data_quality` annotation on `jobs` (currently "always 1.0" or similar from Phase 1) and change to: `0.4 snippet · 0.9 detail-enriched (Phase 2.1, reserved) · 0.7 LLM-enriched (Phase 3, reserved) · 1.0 full structured (no source emits this in Phase 2)`.
- In the ADR list at the bottom of the diagram, add `ADR-0005`.
- Mention `source LIKE 'bing:%'` in the `source` column annotation.

- [ ] **Step 6: Smoke-open each updated diagram**

Run: `ls -la docs/diagrams/`

Expected output shows `phase-2-bing-aggregator-crawl.html` (new), three other `.html` files with fresh mtimes, no `phase-1-testerhome-crawl.html`.

Open each in a browser (`open docs/diagrams/<name>.html`) and confirm it renders. No tests for diagrams — visual gate only.

- [ ] **Step 7: Commit**

```bash
git add docs/diagrams/
git commit -m "docs(diagrams): replace phase-1 with phase-2-bing-aggregator; refresh workflow, module-dep, schema"
```

---

## Task 16: PLAN.md edits (per spec §9)

**Files:**
- Modify: `PLAN.md`

Apply the §9 diff plan verbatim. Use `Edit` with the precise before/after strings below.

- [ ] **Step 1: PLAN.md §1 row 2 (v1 sources)**

Edit `PLAN.md`. Replace:
```
| 2 | v1 sources | Determines crawl mechanism, blockage budget, realism of "comprehensive view" | Lean (2 readable + 1 aggregator) · Aggressive (5+ boards) · Search-engine only | **Lean: TesterHome + Randstad + Bing-aggregator (pluggable `JobSource`)** |
```
with:
```
| 2 | v1 sources | Determines crawl mechanism, blockage budget, realism of "comprehensive view" | Lean (2 readable + 1 aggregator) · Aggressive (5+ boards) · Search-engine only | **Lean: Bing-aggregator (SerpAPI) via pluggable `JobSource`. TesterHome retired in Phase 2 (volume too low for AI-eng market stats); Randstad deferred.** |
```

- [ ] **Step 2: PLAN.md §1 row 4 (Search API)**

Replace:
```
| 4 | Search API | Cost/quota, China-language coverage | Bing · Brave · SerpAPI · Pluggable+Bing | **Bing Web Search v7** (1k free/month, strong zh coverage) |
```
with:
```
| 4 | Search API | Cost/quota, China-language coverage | Bing · Brave · SerpAPI · Pluggable+Bing | **SerpAPI (Bing engine; native Bing v7 retired 2025-08-11)** |
```

- [ ] **Step 3: PLAN.md §3 (Module layout)**

In the `src/jma/sources/` block of the module-layout tree, delete the lines:
```
│   │   ├── browser.py                   # Playwright wrapper
│   │   ├── testerhome.py
│   │   ├── randstad.py
│   │   └── bing.py
```
and replace with:
```
│   │   └── bing.py                     # Phase 2: SerpAPI-backed aggregator
```

In the `src/jma/report/` block, change:
```
│   └── report/
│       ├── render.py
│       └── templates/{market_en.j2, market_zh.j2, fit_en.j2, fit_zh.j2}
```
to:
```
│   └── report/
│       ├── view.py                                          # Phase 2: jma view
│       ├── render.py                                        # Phase 4+
│       └── templates/{view.html.j2, market_en.j2, market_zh.j2, fit_en.j2, fit_zh.j2}
```

In `data/sources/` directory listing, remove `testerhome.yaml` and `randstad.yaml`, keep only `bing.yaml`.

- [ ] **Step 4: PLAN.md §4 Phase 2 heading + body**

Locate `### Phase 2 — Multi-source + blockage robustness · 2 days`. Replace its entire body (down to the next `### Phase 3` heading) with:

```markdown
### Phase 2 — Bing aggregator (SerpAPI), `jma view`, TesterHome retirement · 2 days

Three-part Phase 2:

a. **Retire TesterHome.** Volume too low — as a QA/testing community, "AI agent"
   searches surface mostly test-automation roles; the AI-eng sample is too small
   for meaningful market stats. Delete the source, YAML, tests, live test, and
   phase-1 diagram. Wipe the existing `data/jobs.db` and `data/raw/testerhome/`
   manually (documented; not scripted).
b. **Add the Bing-aggregator via SerpAPI (snippet-only).** Single source class,
   multi-site query template, **no detail-fetch in this phase**. Snippet mapped
   into structured columns (`title`, `posted_at`, `salary`, `experience`);
   raw snippet text stored in `description_text` as Phase 3's LLM-extraction
   input. `source = "bing:<host>"` where `<host>` is the matched `target_sites`
   entry (collapses subdomains; ADR-0005).
c. **Add `jma view`** — a CLI command that renders one self-contained static
   HTML page listing every observation in the latest finished run. Sortable
   client-side via inline ~30-line JS. No web server.

**Real case 2.A — Bing aggregator query construction.** For `--region Hangzhou
--keywords "AI agent"`, after alias expansion:

```
("AI agent") (Hangzhou OR 杭州 OR 杭州市)
  (site:zhipin.com OR site:lagou.com OR site:liepin.com OR site:51job.com OR site:zhaopin.com)
  (招聘 OR hiring OR JD) -inurl:resume
```

One SerpAPI call returns up to 50 organic results. `max_pages=N` maps 1:1 to
N SerpAPI calls (`start = (page - 1) * 50`). The CLI's `--max-pages 5` default
costs 5 SerpAPI queries per crawl, ~20 crawls/month on the free tier.

### Phase 2.1 — Detail-fetch enrichment for Bing — deferred

**Trigger to re-open:** a live SerpAPI sample where at least one target board's
detail pages return useful 200s (i.e. evidence that the anti-bot is *not* uniform
across the target set). **Cost when revived:** extra HTTP budget per crawl, an
`--with-detail`-style flag, the detail outcome matrix from the original spec
draft, and a follow-up ADR-0005 clause on no-halt-on-detail-block. The column
footprint (`url_status`, `url_last_checked_at`, `data_quality=0.9` reserved) is
already in place.
```

- [ ] **Step 5: PLAN.md §5 Risks**

Append three rows to the risks table:

```
| SerpAPI rate-limit (100/mo free) | Tight default `max_pages 5`; 24h URL cache covers SerpAPI page URLs; `--no-cache` opt-out for force-refresh; document the $75/mo dev tier in README if hitting the wall |
| Bing `site:` operator behaviour per board | PLAN intent of cross-board breadth depends on SerpAPI's `site:` behaviour on each board — verify against fixture + opt-in live test before shipping |
| Snippet-only is the floor of Phase 2 data quality | If a future SerpAPI/Bing change degrades snippet content to title-only, Phase 2 silently drops to title+url+date rows. `tests/live/test_bing_live.py` asserts salary/experience/date richness as a tripwire |
```

- [ ] **Step 6: PLAN.md §6 Open items**

Locate the §6 list. Move "Randstad / Playwright / direct-BOSS" entries from Phase 2 narrative to:

```
- Randstad direct crawler, Playwright fallback (`sources/browser.py`), direct
  BOSS Zhipin crawler — **deferred to a later phase or v1.1 if justified.**
  Volume coverage solved by Bing across CN boards.
- **Phase 2.1 — detail-fetch enrichment for Bing.** See Phase 2.1 heading + ADR-0005.
```

- [ ] **Step 7: Commit**

```bash
git add PLAN.md
git commit -m "docs(plan): Phase 2 narrative — SerpAPI snippet-only, jma view, TesterHome retirement, Phase 2.1 deferred"
```

---

## Task 17: README.md, CLAUDE.md, CONTEXT.md edits

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `CONTEXT.md`

- [ ] **Step 1: README.md edits**

Find and replace the following:

- Replace: `The first shipping source is [TesterHome](https://testerhome.com/jobs).`
  With: `The first shipping source is the Bing aggregator via [SerpAPI](https://serpapi.com/) (Bing engine), covering BOSS Zhipin, Lagou, Liepin, 51job, and Zhilian via one `site:` query.`

- Replace: `> **Status:** Phase 0 + Phase 1 of [PLAN.md](PLAN.md) — project bootstrap and\n> the TesterHome vertical slice. Multi-source crawling, LLM extraction, and the\n> reporting CLIs land in later phases.`
  With: `> **Status:** Phase 0 + Phase 1 + Phase 2 of [PLAN.md](PLAN.md) — project bootstrap, the original TesterHome vertical slice (since retired), and the Bing-aggregator + `jma view` shipping surface. LLM extraction and the market/fit reports land in later phases.`

- Add prerequisite: in the **Prerequisites** section, add `- `SERPAPI_KEY` environment variable — sign up at https://serpapi.com (free tier: 100 queries/month).`

- In the **Optional flags** table:
  - Change `--source <name>` default from `testerhome` to `bing`, and update the description: `Which registered source to crawl. Repeatable. Phase 2 ships only `bing` (SerpAPI Bing aggregator).`
  - **Delete the entire row** for `--with-detail` / `--no-detail`.

- Replace the Example output block with:
```
$ export SERPAPI_KEY=...
$ uv run jma crawl --region Hangzhou --keywords "AI agent"
run_id        : 4f8c2a1b7e9d6c5af0d3e89c1a2b3c4d
region        : Hangzhou
keywords      : AI agent
sources:
  bing       : ok    pages=5  jobs=180   elapsed=8.4s
written       : 180 observations to data/jobs.db
```

- Add a new **Verify a crawl** subsection (place it after Example output):
```markdown
### Verify a crawl

`jma view` renders the latest finished run as a self-contained static HTML page
— sortable, no web server, links to each job's URL and per-Run raw blob.

    uv run jma view              # writes data/view.html for the latest finished run
    uv run jma view --open       # also opens it in your default browser
    uv run jma view --run <id>   # render a specific run (full hex id)

If you're starting fresh after the Phase 2 upgrade, wipe the legacy data first:

    rm -f data/jobs.db data/jobs.db-shm data/jobs.db-wal
    rm -rf data/raw/testerhome
```

- [ ] **Step 2: CLAUDE.md edits**

Find and replace:

- Replace: `Phase 1 ships only the TesterHome crawler vertical slice; multi-source, LLM extraction, and reports come in later phases.`
  With: `Phase 1 shipped the TesterHome vertical slice (since retired); Phase 2 replaces it with the Bing aggregator (SerpAPI) plus the `jma view` static-HTML viewer. LLM extraction and the market/fit reports come in later phases.`

- In the `src/jma/` architecture tree, find the lines describing `sources/` and `pipeline/`. After the `pipeline/crawl.py` entry, insert:
```
├── report/           PURE pure: build_view_context(run, jobs, data_root_abs)
│                     -> dict. cli.py view does the I/O (DB read, Jinja2 render,
│                     file write, optional 'open' shell-out).
```

- In the **Source plug-in contract** paragraph, change the example: replace `testerhome` with `bing` and add a note that the `source` field uses the `bing:<host>` form (e.g. `bing:zhipin.com`) per ADR-0005.

- In the **Workflow charts** list, replace the line for `phase-1-testerhome-crawl.html` with:
```
- [phase-2-bing-aggregator-crawl.html](docs/diagrams/phase-2-bing-aggregator-crawl.html) — the Phase-2 crawl pipeline (cli → pipeline → bing source → storage), with per-page SerpAPI fetches and per-Run blob refs.
```

- [ ] **Step 3: CONTEXT.md audit**

Search for `testerhome` mentions:

Run: `grep -n -i testerhome CONTEXT.md`

For each match, decide:
- A `testerhome` example that contrasts with `bing:zhaopin.com` (already present in `[[Job]]` and `[[Source]]` entries): **keep** — both are realistic source-name shapes the glossary should document, and Phase 2.1+ may revive a TesterHome-like direct crawler.
- A line claiming TesterHome is the only shipping source: **rephrase** to make the point source-agnostic.
- A TesterHome-coupled URL freshness example: **keep**; the [[URL freshness]] glossary entry is conceptual and not tied to TesterHome's implementation.

If no source-only-claim lines exist (likely), the glossary is fine as-is.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md CONTEXT.md
git commit -m "docs: README/CLAUDE/CONTEXT — Phase 2 reality (bing aggregator + jma view; TesterHome retired)"
```

---

## Task 18: Final verification gate

**Files:** (none modified — verification only)

This is the merge gate. All of the below MUST pass before claiming Task 001 done.

- [ ] **Step 1: Full non-live test suite**

Run: `uv run pytest -m 'not live' -q`
Expected: every test passes (the `-m 'not live'` filter is the default per `pyproject.toml`). Report the test count; it should be substantially greater than before this phase (new tests: `test_bing.py`, `test_bing_company_heuristic.py`, `test_jobs_for_run.py`, `test_view.py`, `test_view_template.py`, `tests/cli/test_view.py`). If anything fails, halt and fix before continuing.

- [ ] **Step 2: Ruff lint**

Run: `uv run ruff check .`
Expected: `All checks passed!` (or no output). If any error, fix in place — do not add lint exceptions without justification.

- [ ] **Step 3: Ruff format check**

Run: `uv run ruff format --check .`
Expected: `N files already formatted` with N = total py file count. If any file would be reformatted, run `uv run ruff format .` and commit the result with `style: ruff format`.

- [ ] **Step 4: CLI smoke — view --help**

Run: `uv run jma view --help`
Expected: exit 0; usage block lists `--run`, `--out`, `--open` flags.

- [ ] **Step 5: CLI smoke — crawl --help**

Run: `uv run jma crawl --help`
Expected: exit 0; usage block lists `--region`, `--keywords`, `--source` (default `bing`), `--max-pages`, `--max-jobs`, `--no-cache`, `-v / --verbose`. **No `--with-detail` flag.** Verify by grepping the output:

Run: `uv run jma crawl --help 2>&1 | grep -i detail || echo "no detail flag — correct"`
Expected: `no detail flag — correct`.

- [ ] **Step 6: Confirm TesterHome is entirely gone from source**

Run: `grep -rn -i testerhome src/ config/ 2>&1 | grep -v 'No such' || echo "no testerhome refs in source/config"`
Expected: `no testerhome refs in source/config`. (Doc files may still mention TesterHome historically — that's correct.)

- [ ] **Step 7: Smoke-render `jma view` against the live (operator-seeded) DB if present**

Optional gate, only runs if the operator has a real `data/jobs.db` from a recent crawl:

Run: `[ -f data/jobs.db ] && uv run jma view && open data/view.html || echo "skip — no data/jobs.db"`

Expected: either renders + opens (visual verification of the table), or `skip` if no DB.

- [ ] **Step 8: Final commit (only if Step 3 needed `style:` updates)**

If Step 3 produced changes:

```bash
git add -u
git commit -m "style: ruff format"
```

Otherwise: no commit. The plan is complete.

---

## Self-review checklist (done during plan authoring; recorded for the executor)

- [x] **Spec §1 In-scope coverage:** every item maps to a task (1: Tasks 1, 12, 15, 16, 17; 2: Tasks 4, 7, 8; 3: Tasks 10, 11; 4: Task 13; 5: Tasks 16, 17; 6: Task 15; 7: Task 14). DB wipe (4) is operator action only.
- [x] **Spec §1 Out-of-scope:** Randstad / Playwright / LLM extraction / `data/skills.yaml` / market+fit reports / `jma run` / `jma sources status` / `--with-detail` / view filtering+multi-run+aggregates / direct BOSS / live SerpAPI CI / Phase 2.1 detail-fetch — none appear as a task.
- [x] **§2 row 4** `bing:<host>` matched-target-sites rule: Task 8 step 1 + ADR Task 14.
- [x] **§2 row 5** one blob per SerpAPI page: Task 8 step 1 test + step 3 implementation.
- [x] **§2 row 7** `data_quality=0.4` for every row, reserved values documented: Task 8 step 1 assertion + ADR Task 14.
- [x] **§2 row 8** heuristic-only company extraction with `site_names` anchor: Task 7 (full TDD).
- [x] **§2 row 9** SerpAPI fail-fast: Task 2 step 3.
- [x] **§2 row 11** latest-finished-run semantics: Task 5 helper + Task 11 CLI.
- [x] **§2 row 17** per-Run `raw_payload_ref`: Task 5 (schema + helpers + tests).
- [x] **§3.4** `Location.city=None`, `description_text=snippet`: Task 8 step 1 + step 3.
- [x] **§3.5** Pure/effect split: `report/view.py` is pure; `cli.py view` does I/O — Task 10 + Task 11.
- [x] **§5.1** all deletions in Task 1.
- [x] **§5.3** all additions accounted for.
- [x] **§5.4** all edits accounted for (cli.py, base.py, blobs.py, db.py, pyproject.toml, README, PLAN, CLAUDE.md, CONTEXT.md, three diagrams refreshed + one new + one deleted).
- [x] **§6** TDD-first ordering verified — every code-with-logic task has its test step *before* the implementation step.
- [x] **§8 acceptance** demo: `jma crawl` (Task 8 wiring) + `jma view --open` (Task 11) covered by the Task 18 step 4-5-7 smoke.
- [x] **§9** PLAN.md edits in Task 16, row-by-row.
- [x] **§10** ADR-0005 in Task 14 covering all five bullets.

**Type / name consistency:**
- `BingAggregatorSource` is the class name throughout (Task 7 stub, Task 8 full class, Task 9 live test, Task 2 import, Task 12 retarget).
- `build_view_context(run, jobs, data_root_abs)` signature consistent: Task 10 test, Task 10 implementation, Task 11 caller. `data_root_abs` is a `Path` argument that `view.py` stringifies for the context dict key.
- `_heuristic_company_from_title(title, site_name)` signature consistent across Task 7 test, Task 7 stub, Task 8 reuse.
- `_factory_for(source_name, data_root)` — two-arg form throughout after Task 2.
- `jobs_for_run(conn, run_id)` and `latest_finished_run(conn)` — Task 5 test, Task 5 implementation, Task 11 caller.
- DB column `run_jobs.raw_payload_ref` — Task 5 DDL, Task 5 insert, Task 5 select, Task 5 row test, Task 8 indirectly via `insert_jobs`.

No placeholders. Every code step has full content; every command has expected output.

---

## Execution handoff

Plan complete and saved to `docs/2026-05-24-phase-2-bing-view/items/001-plan.md`. The orchestrator (autodev spec-mode) dispatches Task 001 via `superpowers:subagent-driven-development` — one Sonnet subagent per Task above, with checkpointed reviews between tasks. The fixture-presence gate at Task 8 Step 0 is the single operator-attention point in the otherwise-autonomous flow.
