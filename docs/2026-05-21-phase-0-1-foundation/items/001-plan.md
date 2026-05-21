# Phase 0 + Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the `jma` Python project and ship the first vertical slice — `jma crawl --region <text> --keywords <text>` against TesterHome — by implementing every module in `docs/2026-05-21-phase-0-1-foundation/items/001-spec.md` strictly via TDD.

**Architecture:** Pure-function `domain/*` (frozen pydantic v2 models, parsers, dedup, blockage classifier), I/O isolated to `sources/http.py`, `storage/*`, and `cli.py`. Async-first using `httpx.AsyncClient` and `aiosqlite`. Source crawling is configured via YAML, observations stored as `(source, source_internal_id)`-keyed rows with a non-unique `canonical_id` and a `run_jobs` join table for Run membership. Raw HTML blobs gzipped under `data/raw/<source>/<yyyymmdd>/<sha1>.html.gz`.

**Tech Stack:** Python 3.12+, `uv`, `pydantic` v2, `httpx`, `selectolax`, `typer`, `aiosqlite`, `pyyaml`, `pytest`, `pytest-asyncio`, `respx`, `ruff`.

---

## Conventions for this plan

- All file paths are repo-relative to `/Users/snow/Documents/Repository/job-market-agent`.
- Every dep is added with `uv add` (runtime) or `uv add --dev` (test/lint). Every command runs with `uv run …` so the project venv is used.
- Strict TDD: red test → run it → minimal impl → run again → refactor (only if behaviour is preserved) → commit. Code steps are always preceded by a failing-test step in this plan.
- All pydantic models use `model_config = ConfigDict(frozen=True)`. Builders return new instances via `model_copy(update={...})` — never `self.field = x`.
- Pure functions live in `src/jma/domain/`. I/O lives in `src/jma/sources/http.py`, `src/jma/storage/*`, `src/jma/pipeline/crawl.py`, `src/jma/cli.py`.
- We commit at the end of each TDD slice (one green slice = one commit) with a `feat:` / `chore:` / `test:` prefix matching its content.

---

## File Structure (locked in here, mirrored from spec §3)

```
job-market-agent/
├── pyproject.toml                                ← new (Task 0.1)
├── .gitignore                                    ← new (Task 0.1)
├── config/sources/testerhome.yaml                ← new (Task 1.5 / 1.10)
├── data/.gitignore                               ← new (Task 0.1, content: "*")
├── src/jma/__init__.py
├── src/jma/cli.py                                ← Task 1.12
├── src/jma/domain/__init__.py
├── src/jma/domain/models.py                      ← Task 0.2
├── src/jma/domain/normalize.py                   ← Tasks 1.1, 1.2
├── src/jma/domain/blockage.py                    ← Task 1.4
├── src/jma/domain/dedup.py                       ← Task 1.3
├── src/jma/sources/__init__.py
├── src/jma/sources/base.py                       ← Task 1.5
├── src/jma/sources/http.py                       ← Task 1.6
├── src/jma/sources/testerhome.py                 ← Task 1.10
├── src/jma/storage/__init__.py
├── src/jma/storage/db.py                         ← Task 1.7
├── src/jma/storage/cache.py                      ← Task 1.8
├── src/jma/storage/blobs.py                      ← Task 1.9
├── src/jma/pipeline/__init__.py
├── src/jma/pipeline/crawl.py                     ← Task 1.11
└── tests/
    ├── conftest.py
    ├── fixtures/sources/testerhome/listing_ok.html
    ├── fixtures/sources/testerhome/listing_empty.html
    ├── domain/test_models.py
    ├── domain/test_normalize_salary.py
    ├── domain/test_normalize_experience.py
    ├── domain/test_normalize_location.py
    ├── domain/test_blockage.py
    ├── domain/test_dedup.py
    ├── sources/test_source_config.py
    ├── sources/test_http.py
    ├── sources/test_testerhome.py
    ├── storage/test_db.py
    ├── storage/test_cache.py
    ├── storage/test_blobs.py
    ├── pipeline/test_crawl_e2e.py
    ├── cli/test_cli.py
    └── live/test_testerhome_live.py
```

---

## Task 0.1: Project bootstrap (spec slice 0.1)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `data/.gitignore`
- Create: `src/jma/__init__.py`, `src/jma/domain/__init__.py`, `src/jma/sources/__init__.py`, `src/jma/storage/__init__.py`, `src/jma/pipeline/__init__.py`
- Create: `tests/conftest.py`, `tests/domain/__init__.py`, `tests/sources/__init__.py`, `tests/storage/__init__.py`, `tests/pipeline/__init__.py`, `tests/cli/__init__.py`, `tests/live/__init__.py`
- Create: `tests/test_smoke.py`

This slice has no production-code TDD — it sets up the workspace so subsequent slices can run `uv run pytest`. We still write a smoke test first to verify the test runner is wired.

- [ ] **Step 1: Confirm `uv` is on PATH and Python 3.12+ is available**

Run:
```bash
uv --version
uv python find 3.12 || uv python install 3.12
```
Expected: `uv` prints a version. Second command either finds 3.12 or installs it.

- [ ] **Step 2: Initialise `pyproject.toml`**

Create `pyproject.toml` with this exact content:

```toml
[project]
name = "jma"
version = "0.1.0"
description = "Job-market-agent — TesterHome crawl vertical slice"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jma"]

[project.scripts]
jma = "jma.cli:app"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B", "SIM"]

[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = "-m 'not live' -ra"
markers = [
    "live: opt-in tests that hit the real network (skipped by default)",
]
asyncio_mode = "auto"
```

- [ ] **Step 3: Add runtime + dev dependencies via `uv add`**

Run:
```bash
uv add pydantic httpx selectolax typer aiosqlite pyyaml
uv add --dev pytest pytest-asyncio respx ruff
uv lock
```
Expected: `uv.lock` created; `pyproject.toml` updated with the dep lists. No errors.

- [ ] **Step 4: Create `.gitignore` at repo root**

Create `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/
*.egg-info/

# Runtime data
data/
!data/.gitignore

# Editors / OS
.DS_Store
.vscode/
.idea/
```

- [ ] **Step 5: Create `data/.gitignore` (ignore-all)**

Create `data/.gitignore`:

```
*
!.gitignore
```

- [ ] **Step 6: Create empty `__init__.py` files**

Create the following files, each with exactly one comment line so it's not a zero-byte file:

`src/jma/__init__.py`:
```python
"""jma — job-market-agent."""
```

`src/jma/domain/__init__.py`:
```python
"""Pure-function domain layer."""
```

`src/jma/sources/__init__.py`:
```python
"""Per-source crawlers + HTTP wrapper."""
```

`src/jma/storage/__init__.py`:
```python
"""SQLite + blob persistence (I/O boundary)."""
```

`src/jma/pipeline/__init__.py`:
```python
"""Crawl orchestration."""
```

`tests/conftest.py`:
```python
"""Shared pytest fixtures (intentionally empty for now)."""
```

Create empty package markers for test subpackages:
- `tests/domain/__init__.py`
- `tests/sources/__init__.py`
- `tests/storage/__init__.py`
- `tests/pipeline/__init__.py`
- `tests/cli/__init__.py`
- `tests/live/__init__.py`

Each file content:
```python
```

- [ ] **Step 7: Write the smoke test (red)**

Create `tests/test_smoke.py`:

```python
def test_python_runtime_is_3_12_plus() -> None:
    import sys

    assert sys.version_info >= (3, 12)


def test_jma_package_is_importable() -> None:
    import jma

    assert jma.__doc__ is not None
```

- [ ] **Step 8: Run smoke test**

Run: `uv run pytest tests/test_smoke.py -v`

Expected: 2 passed.

- [ ] **Step 9: Run ruff**

Run: `uv run ruff check .`

Expected: `All checks passed!`.

- [ ] **Step 10: Commit slice 0.1**

```bash
git add pyproject.toml uv.lock .gitignore data/.gitignore src/ tests/
git commit -m "chore: bootstrap jma project (uv, ruff, pytest, package skeleton)"
```

---

## Task 0.2: Domain models (spec slice 0.2)

**Files:**
- Create: `src/jma/domain/models.py`
- Create: `tests/domain/test_models.py`

The full v1 model surface lands here so subsequent layers can import stable types. Models are pydantic v2 `BaseModel`s with `model_config = ConfigDict(frozen=True)`. Enums are `str`-valued for clean SQLite serialisation.

- [ ] **Step 1: Write failing tests for models (red)**

Create `tests/domain/test_models.py`:

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jma.domain.models import (
    BlockStatus,
    Experience,
    Job,
    Location,
    Salary,
    SalaryPeriod,
    Seniority,
    SourceResult,
    SourceStatus,
    WorkMode,
)


def _make_job(**overrides) -> Job:
    defaults = dict(
        id="obs-1",
        canonical_id="canon-1",
        source="testerhome",
        title="AI Agent Engineer",
        title_raw="【杭州】AI Agent Engineer 15-30K·14薪",
        location=Location(country="CN", city="Hangzhou"),
        salary=Salary(raw=""),
        experience=Experience(raw=""),
        fetched_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        url="https://testerhome.com/topics/123",
        raw_payload_ref="raw/testerhome/20260521/abc.html.gz",
    )
    return Job(**{**defaults, **overrides})


def test_models_are_frozen() -> None:
    loc = Location(country="CN", city="Hangzhou")
    with pytest.raises(ValidationError):
        loc.city = "Shanghai"  # type: ignore[misc]


def test_location_defaults() -> None:
    loc = Location()
    assert loc.country is None
    assert loc.city is None
    assert loc.district is None
    assert loc.work_mode is WorkMode.UNKNOWN


def test_salary_defaults() -> None:
    s = Salary()
    assert s.min is None
    assert s.max is None
    assert s.currency is None
    assert s.period is SalaryPeriod.UNKNOWN
    assert s.months_per_year is None
    assert s.raw == ""
    assert s.parsed is False


def test_salary_disclosure_three_way() -> None:
    parseable = Salary(min=15000, max=30000, currency="CNY", period=SalaryPeriod.MONTHLY,
                       months_per_year=14, raw="15-30K·14薪", parsed=True)
    unparseable = Salary(raw="面议")
    absent = Salary()
    assert parseable.disclosure == "parseable"
    assert unparseable.disclosure == "unparseable"
    assert absent.disclosure == "absent"


def test_experience_defaults() -> None:
    e = Experience()
    assert e.min_years is None and e.max_years is None and e.raw == ""


def test_block_status_defaults() -> None:
    b = BlockStatus(kind=SourceStatus.OK)
    assert b.reason == "" and b.evidence == ""


def test_job_round_trip() -> None:
    job = _make_job()
    payload = job.model_dump()
    rebuilt = Job.model_validate(payload)
    assert rebuilt == job


def test_job_phase3_fields_default_empty() -> None:
    job = _make_job()
    assert job.skills_raw == []
    assert job.skills_canonical == []
    assert job.seniority is Seniority.UNKNOWN
    assert job.responsibilities_summary == ""
    assert job.description_text == ""
    assert job.data_quality == 1.0


def test_source_result_defaults_jobs_to_empty_tuple() -> None:
    r = SourceResult(source="testerhome", status=SourceStatus.OK)
    assert r.jobs == ()
    assert r.reason == ""
    assert r.pages_fetched == 0
    assert r.elapsed_ms == 0
```

- [ ] **Step 2: Run test — expect ImportError / fail**

Run: `uv run pytest tests/domain/test_models.py -v`
Expected: collection error / fail because `jma.domain.models` does not exist yet.

- [ ] **Step 3: Implement `src/jma/domain/models.py` (green)**

Create `src/jma/domain/models.py`:

```python
"""Frozen pydantic models for the v1 domain surface (spec §4)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WorkMode(str, Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class Seniority(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    LEAD = "lead"
    UNKNOWN = "unknown"


class SalaryPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    DAILY = "daily"
    HOURLY = "hourly"
    UNKNOWN = "unknown"


class SourceStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    country: str | None = None
    city: str | None = None
    district: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN


class Salary(BaseModel):
    model_config = ConfigDict(frozen=True)

    min: int | None = None
    max: int | None = None
    currency: str | None = None
    period: SalaryPeriod = SalaryPeriod.UNKNOWN
    months_per_year: int | None = None
    raw: str = ""
    parsed: bool = False

    @property
    def disclosure(self) -> Literal["parseable", "unparseable", "absent"]:
        if self.parsed:
            return "parseable"
        return "absent" if self.raw == "" else "unparseable"


class Experience(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_years: int | None = None
    max_years: int | None = None
    raw: str = ""


class BlockStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: SourceStatus
    reason: str = ""
    evidence: str = ""


class Job(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    canonical_id: str
    source: str
    source_internal_id: str | None = None
    title: str
    title_raw: str
    company: str | None = None
    location: Location
    salary: Salary
    experience: Experience
    skills_raw: list[str] = []
    skills_canonical: list[str] = []
    seniority: Seniority = Seniority.UNKNOWN
    responsibilities_summary: str = ""
    description_text: str = ""
    posted_at: datetime | None = None
    fetched_at: datetime
    url: str
    raw_payload_ref: str
    data_quality: float = 1.0


class SourceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    status: SourceStatus
    jobs: tuple[Job, ...] = ()
    reason: str = ""
    pages_fetched: int = 0
    elapsed_ms: int = 0


class MarketReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    stats_json: dict[str, object] = {}
    narrative_md: str = ""


class FitReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    profile_id: str = ""
    top_jobs_md: str = ""
    synthesis_md: str = ""
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/domain/test_models.py -v`
Expected: 9 passed.

- [ ] **Step 5: Ruff check**

Run: `uv run ruff check src/jma/domain/models.py tests/domain/test_models.py`
Expected: All checks passed.

- [ ] **Step 6: Commit slice 0.2**

```bash
git add src/jma/domain/models.py tests/domain/test_models.py
git commit -m "feat(domain): add frozen v1 models with Salary.disclosure"
```

---

## Task 1.1: `parse_salary` (spec slice 1.1)

**Files:**
- Create/modify: `src/jma/domain/normalize.py`
- Create: `tests/domain/test_normalize_salary.py`

`parse_salary(raw: str) -> Salary` is a pure function. Unparseable / empty inputs return `Salary(raw=raw)` with `parsed=False` and `currency=None`. Parseable forms set `parsed=True`, `min`/`max` (monthly equivalent only for MONTHLY/ANNUAL), `currency`, `period`, `months_per_year`. DAILY/HOURLY keep numeric figures in `raw` but leave `min`/`max=None`.

Inline parse-corpus (judgment call — spec §1 references "PLAN case 1.A" but PLAN.md is out of scope; this corpus is locked in here):

| # | input | expected |
|---|---|---|
| 1 | `"10-20K"` | min=10000, max=20000, currency="CNY", period=MONTHLY, months=12, parsed=True |
| 2 | `"15-30K·14薪"` | min=15000, max=30000, currency="CNY", period=MONTHLY, months=14, parsed=True |
| 3 | `"15-30k·13薪"` | min=15000, max=30000, currency="CNY", period=MONTHLY, months=13, parsed=True |
| 4 | `"年薪 40-60万"` | min=400000//12, max=600000//12, currency="CNY", period=ANNUAL, months=12, parsed=True |
| 5 | `"面议"` | raw="面议", parsed=False, currency=None |
| 6 | `""` | raw="", parsed=False, currency=None (disclosure="absent") |
| 7 | `"$120K-$160K"` | min=10000, max=13333, currency="USD", period=ANNUAL, months=12, parsed=True (min=120000//12, max=160000//12) |
| 8 | `"  10-20K  "` (whitespace) | same as row 1 after strip |
| 9 | `"１０-２０Ｋ"` (full-width digits + K) | same as row 1 after NFKC |
| 10 | `"15K-30K·14薪"` (explicit K on both) | same as row 2 |
| 11 | `"日薪 800-1200"` | min=None, max=None, currency="CNY", period=DAILY, months=None, parsed=True (DAILY: numeric retained, but min/max=None per spec §2 row 11) |
| 12 | `"时薪 50"` | min=None, max=None, currency="CNY", period=HOURLY, months=None, parsed=True |

Notes:
- DAILY/HOURLY rows still set `parsed=True` so aggregations know the input was numerically expressible; `min`/`max=None` because the spec forbids cross-period conversion at parse time and §2 row 11 says: "min/max are populated only when parsed=True AND period in {MONTHLY, ANNUAL}".
- The annual-to-monthly conversion uses integer floor division.
- Currency detection: leading `$` → USD; otherwise default CNY for the Chinese tokens we support. We do **not** infer currency for the unparseable cases (spec §2 row 11: `currency = None for unparseable`).

- [ ] **Step 1: Write failing tests (red)**

Create `tests/domain/test_normalize_salary.py`:

```python
from jma.domain.models import Salary, SalaryPeriod
from jma.domain.normalize import parse_salary


def test_simple_monthly_range() -> None:
    s = parse_salary("10-20K")
    assert s == Salary(min=10000, max=20000, currency="CNY",
                       period=SalaryPeriod.MONTHLY, months_per_year=12,
                       raw="10-20K", parsed=True)


def test_monthly_with_14_months() -> None:
    s = parse_salary("15-30K·14薪")
    assert s.min == 15000 and s.max == 30000
    assert s.currency == "CNY"
    assert s.period is SalaryPeriod.MONTHLY
    assert s.months_per_year == 14
    assert s.parsed is True


def test_monthly_with_13_months_lowercase_k() -> None:
    s = parse_salary("15-30k·13薪")
    assert s.months_per_year == 13
    assert s.parsed is True


def test_annual_cny_wan() -> None:
    s = parse_salary("年薪 40-60万")
    assert s.period is SalaryPeriod.ANNUAL
    assert s.currency == "CNY"
    assert s.min == 400000 // 12
    assert s.max == 600000 // 12
    assert s.months_per_year == 12
    assert s.parsed is True


def test_unparseable_chinese_competitive() -> None:
    s = parse_salary("面议")
    assert s == Salary(raw="面议")
    assert s.disclosure == "unparseable"


def test_empty_string_is_absent() -> None:
    s = parse_salary("")
    assert s == Salary(raw="")
    assert s.disclosure == "absent"


def test_usd_annual_range() -> None:
    s = parse_salary("$120K-$160K")
    assert s.currency == "USD"
    assert s.period is SalaryPeriod.ANNUAL
    assert s.min == 120000 // 12
    assert s.max == 160000 // 12
    assert s.parsed is True


def test_whitespace_padded_input() -> None:
    s = parse_salary("  10-20K  ")
    assert s.min == 10000 and s.max == 20000
    assert s.parsed is True


def test_full_width_digits_via_nfkc() -> None:
    s = parse_salary("１０-２０Ｋ")
    assert s.min == 10000 and s.max == 20000
    assert s.parsed is True


def test_double_k_explicit() -> None:
    s = parse_salary("15K-30K·14薪")
    assert s.min == 15000 and s.max == 30000 and s.months_per_year == 14


def test_daily_keeps_period_no_minmax() -> None:
    s = parse_salary("日薪 800-1200")
    assert s.period is SalaryPeriod.DAILY
    assert s.currency == "CNY"
    assert s.min is None and s.max is None
    assert s.parsed is True


def test_hourly_keeps_period_no_minmax() -> None:
    s = parse_salary("时薪 50")
    assert s.period is SalaryPeriod.HOURLY
    assert s.currency == "CNY"
    assert s.min is None and s.max is None
    assert s.parsed is True
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/domain/test_normalize_salary.py -v`
Expected: collection error / fail (no `jma.domain.normalize`).

- [ ] **Step 3: Implement `normalize.py` (green)**

Create `src/jma/domain/normalize.py`:

```python
"""Pure parsers for salary, experience, location strings (spec §1)."""
from __future__ import annotations

import re
import unicodedata

from jma.domain.models import Experience, Location, Salary, SalaryPeriod, WorkMode


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _normalize_for_match(s: str) -> str:
    """NFKC + lowercase + whitespace collapse + strip (shared helper, also used by dedup)."""
    folded = _nfkc(s).lower()
    return re.sub(r"\s+", " ", folded).strip()


# -- salary --------------------------------------------------------------

_RE_MONTHLY_K = re.compile(
    r"(?P<min>\d+)\s*[Kk]?\s*[-–]\s*(?P<max>\d+)\s*[Kk](?:\s*·\s*(?P<months>\d+)\s*薪)?"
)
_RE_ANNUAL_WAN = re.compile(r"年薪\s*(?P<min>\d+)\s*[-–]\s*(?P<max>\d+)\s*万")
_RE_USD_ANNUAL = re.compile(
    r"\$\s*(?P<min>\d+)\s*K\s*[-–]\s*\$?\s*(?P<max>\d+)\s*K", re.IGNORECASE
)
_RE_DAILY = re.compile(r"日薪\s*(?P<min>\d+)(?:\s*[-–]\s*(?P<max>\d+))?")
_RE_HOURLY = re.compile(r"时薪\s*(?P<min>\d+)(?:\s*[-–]\s*(?P<max>\d+))?")


def parse_salary(raw: str) -> Salary:
    if raw == "":
        return Salary(raw="")

    s = _nfkc(raw).strip()
    if s == "":
        return Salary(raw=raw)

    # USD annual — check first because it has its own currency.
    m = _RE_USD_ANNUAL.search(s)
    if m:
        lo = int(m["min"]) * 1000
        hi = int(m["max"]) * 1000
        return Salary(min=lo // 12, max=hi // 12, currency="USD",
                      period=SalaryPeriod.ANNUAL, months_per_year=12,
                      raw=raw, parsed=True)

    # CNY annual (年薪 X-Y万).
    m = _RE_ANNUAL_WAN.search(s)
    if m:
        lo = int(m["min"]) * 10000
        hi = int(m["max"]) * 10000
        return Salary(min=lo // 12, max=hi // 12, currency="CNY",
                      period=SalaryPeriod.ANNUAL, months_per_year=12,
                      raw=raw, parsed=True)

    # CNY daily (日薪 X[-Y]).
    m = _RE_DAILY.search(s)
    if m:
        return Salary(min=None, max=None, currency="CNY",
                      period=SalaryPeriod.DAILY, months_per_year=None,
                      raw=raw, parsed=True)

    # CNY hourly (时薪 X[-Y]).
    m = _RE_HOURLY.search(s)
    if m:
        return Salary(min=None, max=None, currency="CNY",
                      period=SalaryPeriod.HOURLY, months_per_year=None,
                      raw=raw, parsed=True)

    # CNY monthly (X-YK[·N薪]).
    m = _RE_MONTHLY_K.search(s)
    if m:
        months = int(m["months"]) if m["months"] else 12
        return Salary(min=int(m["min"]) * 1000, max=int(m["max"]) * 1000,
                      currency="CNY", period=SalaryPeriod.MONTHLY,
                      months_per_year=months, raw=raw, parsed=True)

    return Salary(raw=raw)


# -- experience and location are filled in slice 1.2 ---------------------


def parse_experience(text: str) -> Experience:  # placeholder, real impl in slice 1.2
    raise NotImplementedError


def parse_location(text: str) -> Location:  # placeholder, real impl in slice 1.2
    raise NotImplementedError
```

- [ ] **Step 4: Run tests — expect green**

Run: `uv run pytest tests/domain/test_normalize_salary.py -v`
Expected: 12 passed.

- [ ] **Step 5: Refactor — extract a single fall-through if/elif chain (optional)**

Read the implementation again; the chain of `if m: return …` is already idiomatic and immutable. Skip the refactor — behaviour is preserved only if you don't restructure here. Leave as-is.

- [ ] **Step 6: Commit slice 1.1**

```bash
git add src/jma/domain/normalize.py tests/domain/test_normalize_salary.py
git commit -m "feat(domain): parse_salary handles monthly, annual, USD, daily, hourly, unparseable"
```

---

## Task 1.2: `parse_experience` and `parse_location` (spec slice 1.2)

**Files:**
- Modify: `src/jma/domain/normalize.py`
- Create: `tests/domain/test_normalize_experience.py`
- Create: `tests/domain/test_normalize_location.py`

`parse_experience(text)` accepts free text like `"3-5年经验"`, `"5年以上"`, `"应届"`, `""`. `parse_location(text)` handles TesterHome's `【杭州·余杭】` form, plus `Remote` / `远程` work-mode hints, plus the empty string.

- [ ] **Step 1: Write failing experience tests (red)**

Create `tests/domain/test_normalize_experience.py`:

```python
from jma.domain.models import Experience
from jma.domain.normalize import parse_experience


def test_range_years() -> None:
    e = parse_experience("3-5年经验")
    assert e.min_years == 3 and e.max_years == 5 and e.raw == "3-5年经验"


def test_open_ended_lower_bound() -> None:
    e = parse_experience("5年以上")
    assert e.min_years == 5 and e.max_years is None


def test_fresh_grad() -> None:
    e = parse_experience("应届")
    assert e.min_years == 0 and e.max_years == 0


def test_empty_string() -> None:
    e = parse_experience("")
    assert e == Experience(raw="")


def test_unparseable_keeps_raw() -> None:
    e = parse_experience("经验不限")
    assert e.min_years is None and e.max_years is None
    assert e.raw == "经验不限"
```

- [ ] **Step 2: Write failing location tests (red)**

Create `tests/domain/test_normalize_location.py`:

```python
from jma.domain.models import Location, WorkMode
from jma.domain.normalize import parse_location


def test_testerhome_city_district_brackets() -> None:
    loc = parse_location("【杭州·余杭】AI Agent Engineer")
    assert loc.city == "Hangzhou"
    assert loc.district == "余杭"
    assert loc.country == "CN"


def test_testerhome_city_only_brackets() -> None:
    loc = parse_location("【北京】Senior Backend")
    assert loc.city == "Beijing"
    assert loc.district is None
    assert loc.country == "CN"


def test_remote_chinese() -> None:
    loc = parse_location("【远程】Test Engineer")
    assert loc.work_mode is WorkMode.REMOTE


def test_remote_english() -> None:
    loc = parse_location("Remote · Test Engineer")
    assert loc.work_mode is WorkMode.REMOTE


def test_empty_input_returns_unknown_location() -> None:
    loc = parse_location("")
    assert loc == Location()


def test_no_brackets_no_city() -> None:
    loc = parse_location("Senior Backend at FooCorp")
    assert loc.city is None and loc.district is None
```

- [ ] **Step 3: Run both — expect fail**

Run: `uv run pytest tests/domain/test_normalize_experience.py tests/domain/test_normalize_location.py -v`
Expected: `NotImplementedError` for every test.

- [ ] **Step 4: Implement `parse_experience` + `parse_location` (green)**

Edit `src/jma/domain/normalize.py`, replace the two placeholder functions with:

```python
# -- experience ----------------------------------------------------------

_RE_EXP_RANGE = re.compile(r"(?P<min>\d+)\s*[-–]\s*(?P<max>\d+)\s*年")
_RE_EXP_OPEN = re.compile(r"(?P<min>\d+)\s*年以上")
_FRESH_TOKENS = ("应届", "fresh graduate", "fresh-grad")


def parse_experience(text: str) -> Experience:
    if text == "":
        return Experience(raw="")
    s = _nfkc(text)
    lower = s.lower()
    if any(tok in lower for tok in _FRESH_TOKENS) or "应届" in s:
        return Experience(min_years=0, max_years=0, raw=text)
    m = _RE_EXP_RANGE.search(s)
    if m:
        return Experience(min_years=int(m["min"]), max_years=int(m["max"]), raw=text)
    m = _RE_EXP_OPEN.search(s)
    if m:
        return Experience(min_years=int(m["min"]), max_years=None, raw=text)
    return Experience(raw=text)


# -- location ------------------------------------------------------------

_CITY_PINYIN: dict[str, str] = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "杭州": "Hangzhou",
    "深圳": "Shenzhen",
    "广州": "Guangzhou",
    "南京": "Nanjing",
    "成都": "Chengdu",
    "苏州": "Suzhou",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "重庆": "Chongqing",
}

_RE_BRACKET = re.compile(r"【\s*(?P<inside>[^】]+?)\s*】")
_REMOTE_TOKENS_CN = ("远程",)
_REMOTE_TOKENS_EN = ("remote",)


def parse_location(text: str) -> Location:
    if text == "":
        return Location()
    s = _nfkc(text)
    lower = s.lower()

    work_mode = WorkMode.UNKNOWN
    if any(tok in s for tok in _REMOTE_TOKENS_CN) or any(tok in lower for tok in _REMOTE_TOKENS_EN):
        work_mode = WorkMode.REMOTE

    m = _RE_BRACKET.search(s)
    if not m:
        return Location(work_mode=work_mode)

    inside = m["inside"].strip()
    # Inside is either "city" or "city·district" or "远程".
    if inside in _REMOTE_TOKENS_CN:
        return Location(work_mode=WorkMode.REMOTE)

    parts = [p.strip() for p in inside.split("·") if p.strip()]
    city_native = parts[0] if parts else ""
    district = parts[1] if len(parts) > 1 else None
    city = _CITY_PINYIN.get(city_native)
    if city is None:
        # Unknown native city: keep native form in district, leave city blank.
        return Location(country="CN", city=None, district=city_native, work_mode=work_mode)
    return Location(country="CN", city=city, district=district, work_mode=work_mode)
```

- [ ] **Step 5: Run tests — expect green**

Run: `uv run pytest tests/domain/test_normalize_experience.py tests/domain/test_normalize_location.py -v`
Expected: 5 + 6 = 11 passed.

- [ ] **Step 6: Run full normalize test set + ruff**

Run:
```bash
uv run pytest tests/domain/ -v
uv run ruff check src/jma/domain/ tests/domain/
```
Expected: all green; ruff clean.

- [ ] **Step 7: Commit slice 1.2**

```bash
git add src/jma/domain/normalize.py tests/domain/test_normalize_experience.py tests/domain/test_normalize_location.py
git commit -m "feat(domain): parse_experience + parse_location with city pinyin map"
```

---

## Task 1.3: Dedup (spec slice 1.3)

**Files:**
- Create: `src/jma/domain/dedup.py`
- Create: `tests/domain/test_dedup.py`

`job_id(source, internal_id, title, company, city)` returns
`sha1(f"{source}:{internal_id}")` when `internal_id` is non-empty, else
`sha1(f"{source}:{normalize(title)}|{normalize(company)}|{normalize(city)}")`.
`canonical_id(title, company, city)` returns
`sha1(f"{normalize(title)}|{normalize(company)}|{normalize(city)}")` and is
source-independent.

`normalize(value)` for dedup uses `_normalize_for_match` from `normalize.py` (NFKC + lowercase + whitespace-collapse + strip). `None` → `""`.

- [ ] **Step 1: Write failing dedup tests (red)**

Create `tests/domain/test_dedup.py`:

```python
from jma.domain.dedup import canonical_id, job_id


def test_job_id_deterministic_with_internal_id() -> None:
    a = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    b = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    assert a == b


def test_job_id_source_scoped() -> None:
    a = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    b = job_id(source="bing:zhaopin.com", internal_id="123", title="X", company="Y", city="Hangzhou")
    assert a != b


def test_job_id_fallback_when_internal_id_missing() -> None:
    a = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Hangzhou")
    b = job_id(source="testerhome", internal_id="",
               title="AI Engineer", company="Foo", city="Hangzhou")
    assert a == b  # both fall back to title|company|city
    c = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Shanghai")
    assert a != c


def test_job_id_fallback_nfkc_and_whitespace_collapse() -> None:
    # Full-width title + extra whitespace should collapse to the same id.
    a = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Hangzhou")
    b = job_id(source="testerhome", internal_id=None,
               title="ＡＩ  Engineer", company="foo", city=" Hangzhou ")
    assert a == b


def test_canonical_id_deterministic() -> None:
    a = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    b = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    assert a == b


def test_canonical_id_source_independent() -> None:
    # Two observations from two sources of the *same* posting share canonical id.
    obs_testerhome = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    obs_bing = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    assert obs_testerhome == obs_bing


def test_canonical_id_normalises_inputs() -> None:
    a = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    b = canonical_id(title="ai engineer", company="FOO", city=" hangzhou ")
    c = canonical_id(title="ＡＩ engineer", company="foo", city="Hangzhou")
    assert a == b == c


def test_canonical_id_handles_none() -> None:
    a = canonical_id(title="AI Engineer", company=None, city=None)
    b = canonical_id(title="ai engineer", company="", city="")
    assert a == b
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/domain/test_dedup.py -v`
Expected: collection error / fail (no `jma.domain.dedup`).

- [ ] **Step 3: Implement `dedup.py` (green)**

Create `src/jma/domain/dedup.py`:

```python
"""Pure dedup keys (spec §2 row 4 / ADR-0001)."""
from __future__ import annotations

import hashlib

from jma.domain.normalize import _normalize_for_match


def _norm(value: str | None) -> str:
    if value is None:
        return ""
    return _normalize_for_match(value)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def job_id(
    *,
    source: str,
    internal_id: str | None,
    title: str,
    company: str | None,
    city: str | None,
) -> str:
    """JobObservation id. Source-scoped. Uses internal_id when present, else title|company|city."""
    if internal_id:
        return _sha1(f"{source}:{internal_id}")
    payload = f"{source}:{_norm(title)}|{_norm(company)}|{_norm(city)}"
    return _sha1(payload)


def canonical_id(*, title: str, company: str | None, city: str | None) -> str:
    """Job (cross-source) id. Source-independent."""
    return _sha1(f"{_norm(title)}|{_norm(company)}|{_norm(city)}")
```

- [ ] **Step 4: Expose `_normalize_for_match` as a public-ish helper**

Edit `src/jma/domain/normalize.py` and add a public alias at module scope, **without** removing the underscore-prefixed name (other modules already import it):

```python
normalize_for_match = _normalize_for_match
```

- [ ] **Step 5: Run dedup tests — expect green**

Run: `uv run pytest tests/domain/test_dedup.py -v`
Expected: 8 passed.

- [ ] **Step 6: Ruff + commit**

Run: `uv run ruff check src/jma/domain/ tests/domain/`
Expected: clean.

```bash
git add src/jma/domain/dedup.py src/jma/domain/normalize.py tests/domain/test_dedup.py
git commit -m "feat(domain): job_id (source-scoped) + canonical_id (cross-source)"
```

---

## Task 1.4: Blockage classifier (spec slice 1.4)

**Files:**
- Create: `src/jma/domain/blockage.py`
- Create: `tests/domain/test_blockage.py`

The classifier is pure: `classify(status_code, headers, body_text, cfg)` returns a `BlockStatus`. `cfg` is a `SourceConfig` (defined in slice 1.5) but the classifier only reads `cfg.content_block_markers`. To avoid an import cycle we define a tiny `_BlockClassifierConfig` Protocol locally **and** accept the full `SourceConfig` via duck typing. We will register the real `SourceConfig` in slice 1.5.

Decision tree (first match wins) — verbatim spec §6:

1. `status_code == 429` → `RATE_LIMITED`, `reason="HTTP 429; Retry-After=<header or '?'>s"`.
2. `status_code in {401, 403}` → `BLOCKED`, `reason="HTTP <code>"`.
3. `status_code >= 500` → `ERROR`, `reason="HTTP <code>"`.
4. `status_code != 200` → `ERROR`, `reason="HTTP <code>"`.
5. any `marker in body_text` → `BLOCKED`, `reason="soft-block: <marker>"`, `evidence=snippet_around(body, marker, 120)`.
6. `body_text == ""` → `ERROR`, `reason="empty response body"`.
7. otherwise → `OK`.

`snippet_around(text, marker, radius=120)` returns `text[max(0, i-radius):i+len(marker)+radius]` with whitespace runs collapsed to single spaces. Capped at ≤200 chars (we truncate to 200 if the slice is longer than that — defensive: `radius=120` * 2 + marker length could exceed 200 for long markers).

- [ ] **Step 1: Write failing blockage tests (red)**

Create `tests/domain/test_blockage.py`:

```python
from dataclasses import dataclass

from jma.domain.blockage import classify, snippet_around
from jma.domain.models import BlockStatus, SourceStatus


@dataclass(frozen=True)
class _Cfg:
    content_block_markers: tuple[str, ...] = ()


def test_429_rate_limited_with_retry_after() -> None:
    b = classify(429, {"retry-after": "30"}, "anything", _Cfg())
    assert b.kind is SourceStatus.RATE_LIMITED
    assert "Retry-After=30" in b.reason


def test_429_without_retry_after() -> None:
    b = classify(429, {}, "anything", _Cfg())
    assert b.kind is SourceStatus.RATE_LIMITED
    assert "Retry-After=?" in b.reason


def test_403_blocked() -> None:
    b = classify(403, {}, "x", _Cfg())
    assert b.kind is SourceStatus.BLOCKED
    assert b.reason == "HTTP 403"


def test_5xx_error() -> None:
    b = classify(503, {}, "x", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "HTTP 503"


def test_other_non_200_error() -> None:
    b = classify(302, {}, "x", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "HTTP 302"


def test_soft_block_marker_match() -> None:
    cfg = _Cfg(content_block_markers=("访问受限",))
    b = classify(200, {}, "前文 访问受限 后文", cfg)
    assert b.kind is SourceStatus.BLOCKED
    assert "soft-block: 访问受限" in b.reason
    assert "访问受限" in b.evidence


def test_empty_body_is_error() -> None:
    b = classify(200, {}, "", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "empty response body"


def test_ok_when_status_200_and_body_present() -> None:
    b = classify(200, {}, "<html>jobs</html>", _Cfg())
    assert b == BlockStatus(kind=SourceStatus.OK)


def test_snippet_around_collapses_whitespace() -> None:
    text = "abc    \n DEF  marker   tail  \n\n end"
    out = snippet_around(text, "marker", radius=5)
    assert "  " not in out  # all whitespace runs collapsed
    assert "marker" in out


def test_evidence_capped_at_200_chars() -> None:
    long = "x" * 1000 + "MARK" + "y" * 1000
    cfg = _Cfg(content_block_markers=("MARK",))
    b = classify(200, {}, long, cfg)
    assert len(b.evidence) <= 200
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/domain/test_blockage.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `blockage.py` (green)**

Create `src/jma/domain/blockage.py`:

```python
"""Pure blockage classifier (spec §6). No I/O, no globals, no clock."""
from __future__ import annotations

import re
from typing import Mapping, Protocol

from jma.domain.models import BlockStatus, SourceStatus

_MAX_EVIDENCE = 200


class _HasMarkers(Protocol):
    content_block_markers: tuple[str, ...]


def snippet_around(text: str, marker: str, radius: int) -> str:
    i = text.find(marker)
    if i == -1:
        return ""
    start = max(0, i - radius)
    end = i + len(marker) + radius
    raw = text[start:end]
    collapsed = re.sub(r"\s+", " ", raw).strip()
    if len(collapsed) > _MAX_EVIDENCE:
        collapsed = collapsed[:_MAX_EVIDENCE]
    return collapsed


def classify(
    status_code: int,
    headers: Mapping[str, str],
    body_text: str,
    cfg: _HasMarkers,
) -> BlockStatus:
    if status_code == 429:
        retry = headers.get("retry-after") or headers.get("Retry-After") or "?"
        return BlockStatus(kind=SourceStatus.RATE_LIMITED,
                           reason=f"HTTP 429; Retry-After={retry}s")
    if status_code in (401, 403):
        return BlockStatus(kind=SourceStatus.BLOCKED, reason=f"HTTP {status_code}")
    if status_code >= 500:
        return BlockStatus(kind=SourceStatus.ERROR, reason=f"HTTP {status_code}")
    if status_code != 200:
        return BlockStatus(kind=SourceStatus.ERROR, reason=f"HTTP {status_code}")

    for marker in cfg.content_block_markers:
        if marker in body_text:
            return BlockStatus(
                kind=SourceStatus.BLOCKED,
                reason=f"soft-block: {marker}",
                evidence=snippet_around(body_text, marker, 120),
            )

    if body_text == "":
        return BlockStatus(kind=SourceStatus.ERROR, reason="empty response body")

    return BlockStatus(kind=SourceStatus.OK)
```

- [ ] **Step 4: Run — expect green**

Run: `uv run pytest tests/domain/test_blockage.py -v`
Expected: 10 passed.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src/jma/domain/blockage.py tests/domain/test_blockage.py
git add src/jma/domain/blockage.py tests/domain/test_blockage.py
git commit -m "feat(domain): blockage.classify decision tree + snippet_around"
```

---

## Task 1.5: `JobSource` Protocol + `SourceConfig` (spec slice 1.5)

**Files:**
- Create: `src/jma/sources/base.py`
- Create: `config/sources/testerhome.yaml`
- Create: `tests/sources/test_source_config.py`

`SourceConfig` is a frozen pydantic model. `load_source_config(path)` reads YAML, returns a `SourceConfig`. Missing required keys raise `pydantic.ValidationError`.

- [ ] **Step 1: Write the YAML fixture (no test yet)**

Create `config/sources/testerhome.yaml`:

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

- [ ] **Step 2: Write failing config test (red)**

Create `tests/sources/test_source_config.py`:

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jma.sources.base import JobSource, SourceConfig, load_source_config

REPO = Path(__file__).resolve().parents[2]


def test_loads_testerhome_yaml() -> None:
    cfg = load_source_config(REPO / "config/sources/testerhome.yaml")
    assert isinstance(cfg, SourceConfig)
    assert cfg.name == "testerhome"
    assert cfg.base_url == "https://testerhome.com"
    assert cfg.listing.url_template.endswith("/jobs?page={page}")
    assert cfg.listing.list_item_selector == ".topics .topic"
    assert cfg.listing.title_selector == ".title a"
    assert cfg.listing.href_attr == "href"
    assert cfg.listing.posted_at_attr == ".time@title"
    assert cfg.detail.body_selector == ".topic-detail .markdown-body"
    assert cfg.requires_browser is False
    assert cfg.content_block_markers == ()
    assert cfg.known_good_list_selector == ".topics .topic"
    assert cfg.rate.delay_ms == 800
    assert cfg.rate.max_retries == 3
    assert cfg.rate.backoff_base_s == 2


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"name": "x"}))  # no base_url, listing, etc.
    with pytest.raises(ValidationError):
        load_source_config(bad)


def test_jobsource_protocol_runtime_checkable() -> None:
    # A trivial class matching the Protocol signature should pass isinstance.
    class _Fake:
        name = "fake"
        async def crawl(self, region, keywords, max_pages, max_jobs):
            return None
    assert isinstance(_Fake(), JobSource)
```

- [ ] **Step 3: Run — expect ImportError**

Run: `uv run pytest tests/sources/test_source_config.py -v`
Expected: collection error (no `jma.sources.base`).

- [ ] **Step 4: Implement `sources/base.py` (green)**

Create `src/jma/sources/base.py`:

```python
"""JobSource Protocol + SourceConfig loader (spec §7.1, §7.2)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict

from jma.domain.models import SourceResult


class ListingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    url_template: str
    list_item_selector: str
    title_selector: str
    href_attr: str
    posted_at_attr: str


class DetailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    body_selector: str


class RateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    delay_ms: int = 800
    max_retries: int = 3
    backoff_base_s: int = 2


class SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    base_url: str
    listing: ListingConfig
    detail: DetailConfig
    requires_browser: bool = False
    content_block_markers: tuple[str, ...] = ()
    known_good_list_selector: str
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

- [ ] **Step 5: Run — expect green**

Run: `uv run pytest tests/sources/test_source_config.py -v`
Expected: 3 passed.

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/jma/sources/base.py tests/sources/test_source_config.py config/sources/
git add src/jma/sources/base.py config/sources/testerhome.yaml tests/sources/test_source_config.py
git commit -m "feat(sources): SourceConfig + JobSource Protocol + testerhome.yaml"
```

---

## Task 1.6: Async HTTP client (spec slice 1.6)

**Files:**
- Create: `src/jma/sources/http.py`
- Create: `tests/sources/test_http.py`

`AsyncHttpClient.fetch(url) -> FetchResult(status_code, headers, body, attempts)`. Retries on `429` and `5xx` with exponential backoff (`backoff_base_s ** attempt`) up to `max_retries`. `403`/`401` are returned immediately (no retry — they're real blocks). Sleeps via an injected `sleep` callable so tests run fast.

We do **not** call the classifier here — that is the source-loop's job (spec §7.3). The HTTP client only delivers `(status_code, headers, body)`.

- [ ] **Step 1: Write failing http tests (red)**

Create `tests/sources/test_http.py`:

```python
import asyncio
from typing import Any

import httpx
import pytest
import respx

from jma.sources.base import RateConfig
from jma.sources.http import AsyncHttpClient


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def fake_sleep(sleeps: list[float]):
    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
    return _sleep


@respx.mock
@pytest.mark.asyncio
async def test_fetch_200_first_try(fake_sleep, sleeps) -> None:
    respx.get("https://example.com/x").mock(return_value=httpx.Response(200, text="hi"))
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 200
    assert result.body == "hi"
    assert result.attempts == 1
    assert sleeps == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_403_returned_without_retry(fake_sleep, sleeps) -> None:
    respx.get("https://example.com/x").mock(return_value=httpx.Response(403, text="forbid"))
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 403
    assert result.attempts == 1
    assert sleeps == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_429_then_200_with_backoff(fake_sleep, sleeps) -> None:
    route = respx.get("https://example.com/x")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "1"}, text=""),
        httpx.Response(200, text="ok"),
    ]
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 200
    assert result.attempts == 2
    # First retry waits backoff_base_s ** 1 = 2s.
    assert sleeps == [2]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_5xx_exhausts_retries(fake_sleep, sleeps) -> None:
    route = respx.get("https://example.com/x")
    route.side_effect = [httpx.Response(503, text="")] * 4  # initial + 3 retries
    async with httpx.AsyncClient() as ac:
        client = AsyncHttpClient(ac, rate=RateConfig(max_retries=3, backoff_base_s=2), sleep=fake_sleep)
        result = await client.fetch("https://example.com/x")
    assert result.status_code == 503
    assert result.attempts == 4
    assert sleeps == [2, 4, 8]  # 2^1, 2^2, 2^3
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/sources/test_http.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `sources/http.py` (green)**

Create `src/jma/sources/http.py`:

```python
"""Async HTTP wrapper with retry/backoff (spec §6 + slice 1.6).

Retry policy:
- status 429 or >= 500 → retry up to max_retries with exponential backoff
  (backoff_base_s ** attempt_index, starting at 1).
- status 401/403/other non-200 → return immediately (no retry).
- network errors propagate as httpx exceptions; callers may catch.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from jma.sources.base import RateConfig


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    headers: dict[str, str]
    body: str
    attempts: int


_SleepFn = Callable[[float], Awaitable[None]]


class AsyncHttpClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        rate: RateConfig,
        sleep: _SleepFn | None = None,
    ) -> None:
        self._client = client
        self._rate = rate
        self._sleep: _SleepFn = sleep or asyncio.sleep

    async def fetch(self, url: str) -> FetchResult:
        attempts = 0
        last: httpx.Response | None = None
        while True:
            attempts += 1
            resp = await self._client.get(url)
            last = resp
            should_retry = resp.status_code == 429 or resp.status_code >= 500
            if not should_retry or attempts > self._rate.max_retries:
                return FetchResult(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp.text,
                    attempts=attempts,
                )
            await self._sleep(self._rate.backoff_base_s ** attempts)
```

- [ ] **Step 4: Run — expect green**

Run: `uv run pytest tests/sources/test_http.py -v`
Expected: 4 passed.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src/jma/sources/http.py tests/sources/test_http.py
git add src/jma/sources/http.py tests/sources/test_http.py
git commit -m "feat(sources): AsyncHttpClient with 429/5xx retry + injected sleep"
```

---

## Task 1.7: Storage — SQLite schema, runs, jobs, run_jobs (spec slice 1.7)

**Files:**
- Create: `src/jma/storage/db.py`
- Create: `tests/storage/test_db.py`

`open_db(path)` returns an `aiosqlite.Connection` with schema bootstrapped. `start_run(conn, region, keywords) -> run_id`, `finish_run(conn, run_id, source_results)`, `insert_jobs(conn, run_id, jobs)`.

- [ ] **Step 1: Write failing db tests (red)**

Create `tests/storage/test_db.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SalaryPeriod,
    SourceResult,
    SourceStatus,
)
from jma.storage.db import finish_run, insert_jobs, open_db, start_run


def _job(source: str, internal_id: str, title: str, company: str, city: str) -> Job:
    return Job(
        id=job_id(source=source, internal_id=internal_id, title=title, company=company, city=city),
        canonical_id=canonical_id(title=title, company=company, city=city),
        source=source,
        source_internal_id=internal_id,
        title=title,
        title_raw=title,
        company=company,
        location=Location(country="CN", city=city),
        salary=Salary(raw=""),
        experience=Experience(raw=""),
        fetched_at=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
        url=f"https://example.com/{internal_id}",
        raw_payload_ref=f"raw/{source}/20260521/abc.html.gz",
    )


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "jobs.db"
    async with await open_db(p) as conn:
        pass
    # Second open must not raise.
    async with await open_db(p) as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        names = [r[0] for r in await cur.fetchall()]
    assert set(names) >= {"jobs", "runs", "run_jobs", "url_cache"}


@pytest.mark.asyncio
async def test_start_and_finish_run(tmp_path: Path) -> None:
    async with await open_db(tmp_path / "jobs.db") as conn:
        run_id = await start_run(conn, region="Hangzhou", keywords=("AI agent",))
        assert isinstance(run_id, str) and len(run_id) == 32  # uuid4().hex
        await finish_run(
            conn,
            run_id=run_id,
            source_results=[SourceResult(source="testerhome", status=SourceStatus.OK,
                                         pages_fetched=1, elapsed_ms=100)],
        )
        cur = await conn.execute("SELECT region, keywords_json, source_results_json FROM runs WHERE id=?", (run_id,))
        row = await cur.fetchone()
    assert row[0] == "Hangzhou"
    assert "AI agent" in row[1]
    assert "testerhome" in row[2]


@pytest.mark.asyncio
async def test_insert_jobs_replace_and_run_edges(tmp_path: Path) -> None:
    async with await open_db(tmp_path / "jobs.db") as conn:
        run_id = await start_run(conn, region="Hangzhou", keywords=("AI",))
        j = _job("testerhome", "123", "AI Agent", "Foo", "Hangzhou")
        # Insert twice; the second should REPLACE, not error.
        await insert_jobs(conn, run_id, [j, j])
        cur = await conn.execute("SELECT COUNT(*) FROM jobs WHERE id=?", (j.id,))
        assert (await cur.fetchone())[0] == 1
        cur = await conn.execute("SELECT COUNT(*) FROM run_jobs WHERE run_id=? AND job_id=?", (run_id, j.id))
        assert (await cur.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_group_by_canonical_id_two_sources(tmp_path: Path) -> None:
    """Two observations from different sources of the same canonical job
    group to one row."""
    async with await open_db(tmp_path / "jobs.db") as conn:
        run_id = await start_run(conn, region="Hangzhou", keywords=("AI",))
        j_th = _job("testerhome", "123", "AI Agent", "Foo", "Hangzhou")
        j_bing = _job("bing:zhaopin.com", "z-456", "AI Agent", "Foo", "Hangzhou")
        assert j_th.canonical_id == j_bing.canonical_id  # by construction
        await insert_jobs(conn, run_id, [j_th, j_bing])
        cur = await conn.execute(
            "SELECT canonical_id, COUNT(*) FROM jobs GROUP BY canonical_id"
        )
        rows = await cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == 2  # two observations, one Job
```

- [ ] **Step 2: Run — expect collection / import error**

Run: `uv run pytest tests/storage/test_db.py -v`
Expected: fail (no module).

- [ ] **Step 3: Implement `storage/db.py` (green)**

Create `src/jma/storage/db.py`:

```python
"""SQLite bootstrap + Run / Job persistence (spec §5)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import aiosqlite

from jma.domain.models import Job, SourceResult

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id                  TEXT PRIMARY KEY,
    region              TEXT NOT NULL,
    keywords_json       TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    source_results_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_region_started ON runs(region, started_at);

CREATE TABLE IF NOT EXISTS jobs (
    id                       TEXT PRIMARY KEY,
    canonical_id             TEXT NOT NULL,
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
    salary_parsed            INTEGER NOT NULL,
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
    url_sha1     TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    source       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    status_code  INTEGER NOT NULL,
    blob_ref     TEXT
);

CREATE INDEX IF NOT EXISTS idx_url_cache_fetched ON url_cache(fetched_at);
"""


async def open_db(path: str | Path) -> aiosqlite.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(p))
    await conn.executescript(_DDL)
    await conn.commit()
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def start_run(conn: aiosqlite.Connection, region: str, keywords: tuple[str, ...]) -> str:
    run_id = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO runs (id, region, keywords_json, started_at) VALUES (?,?,?,?)",
        (run_id, region, json.dumps(list(keywords)), _utc_now_iso()),
    )
    await conn.commit()
    return run_id


async def finish_run(
    conn: aiosqlite.Connection,
    run_id: str,
    source_results: Iterable[SourceResult],
) -> None:
    payload = [
        {"source": r.source, "status": r.status.value, "reason": r.reason,
         "pages_fetched": r.pages_fetched, "elapsed_ms": r.elapsed_ms}
        for r in source_results
    ]
    await conn.execute(
        "UPDATE runs SET finished_at=?, source_results_json=? WHERE id=?",
        (_utc_now_iso(), json.dumps(payload), run_id),
    )
    await conn.commit()


def _job_to_row(j: Job) -> tuple:
    return (
        j.id, j.canonical_id, j.source, j.source_internal_id,
        j.title, j.title_raw, j.company,
        j.location.country, j.location.city, j.location.district, j.location.work_mode.value,
        j.salary.min, j.salary.max, j.salary.currency, j.salary.period.value,
        j.salary.months_per_year, j.salary.raw, 1 if j.salary.parsed else 0,
        j.experience.min_years, j.experience.max_years, j.experience.raw,
        json.dumps(list(j.skills_raw)), json.dumps(list(j.skills_canonical)),
        j.seniority.value, j.responsibilities_summary, j.description_text,
        j.posted_at.isoformat() if j.posted_at else None,
        j.fetched_at.isoformat(), j.url, j.raw_payload_ref, j.data_quality,
    )


_INSERT_JOB = """
INSERT OR REPLACE INTO jobs (
  id, canonical_id, source, source_internal_id,
  title, title_raw, company,
  location_country, location_city, location_district, location_work_mode,
  salary_min, salary_max, salary_currency, salary_period,
  salary_months_per_year, salary_raw, salary_parsed,
  experience_min_years, experience_max_years, experience_raw,
  skills_raw_json, skills_canonical_json,
  seniority, responsibilities_summary, description_text,
  posted_at, fetched_at, url, raw_payload_ref, data_quality
) VALUES (?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?, ?,?,?, ?,?,?,?,?)
"""


async def insert_jobs(
    conn: aiosqlite.Connection,
    run_id: str,
    jobs: Iterable[Job],
) -> None:
    rows = [_job_to_row(j) for j in jobs]
    if not rows:
        return
    await conn.executemany(_INSERT_JOB, rows)
    await conn.executemany(
        "INSERT OR IGNORE INTO run_jobs (run_id, job_id) VALUES (?, ?)",
        [(run_id, j.id) for j in jobs],
    )
    await conn.commit()
```

- [ ] **Step 4: Run — expect green**

Run: `uv run pytest tests/storage/test_db.py -v`
Expected: 4 passed.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src/jma/storage/db.py tests/storage/test_db.py
git add src/jma/storage/db.py tests/storage/test_db.py
git commit -m "feat(storage): SQLite bootstrap + start_run/finish_run/insert_jobs"
```

---

## Task 1.8: URL cache (spec slice 1.8)

**Files:**
- Create: `src/jma/storage/cache.py`
- Create: `tests/storage/test_cache.py`

`cache.get(conn, url, *, now=None)` returns the cached `(blob_ref, fetched_at, status_code)` iff fresh (`now - fetched_at < 24h` AND `status_code == 200`). Else returns `None`. `cache.put(conn, url, source, status_code, blob_ref, *, now=None)` upserts via `INSERT OR REPLACE`.

We inject `now` so TTL boundary tests are deterministic.

- [ ] **Step 1: Write failing cache tests (red)**

Create `tests/storage/test_cache.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jma.storage.cache import get, put
from jma.storage.db import open_db

UTC = timezone.utc


@pytest.mark.asyncio
async def test_put_then_get_fresh(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    async with await open_db(tmp_path / "jobs.db") as conn:
        await put(conn, url="https://x/y", source="testerhome",
                  status_code=200, blob_ref="raw/testerhome/20260521/aa.html.gz", now=t0)
        got = await get(conn, url="https://x/y", now=t0 + timedelta(hours=23, minutes=59))
    assert got is not None
    assert got.blob_ref == "raw/testerhome/20260521/aa.html.gz"


@pytest.mark.asyncio
async def test_get_stale_past_24h(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    async with await open_db(tmp_path / "jobs.db") as conn:
        await put(conn, url="https://x/y", source="testerhome",
                  status_code=200, blob_ref="ref", now=t0)
        got = await get(conn, url="https://x/y", now=t0 + timedelta(hours=24, minutes=1))
    assert got is None


@pytest.mark.asyncio
async def test_non_200_is_never_fresh(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    async with await open_db(tmp_path / "jobs.db") as conn:
        await put(conn, url="https://x/y", source="testerhome",
                  status_code=429, blob_ref=None, now=t0)
        got = await get(conn, url="https://x/y", now=t0 + timedelta(minutes=1))
    assert got is None


@pytest.mark.asyncio
async def test_miss_when_not_inserted(tmp_path: Path) -> None:
    async with await open_db(tmp_path / "jobs.db") as conn:
        got = await get(conn, url="https://nope", now=datetime.now(UTC))
    assert got is None
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/storage/test_cache.py -v`
Expected: fail.

- [ ] **Step 3: Implement `storage/cache.py` (green)**

Create `src/jma/storage/cache.py`:

```python
"""24h URL cache (spec §5 cache TTL)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class CacheHit:
    url: str
    blob_ref: str | None
    fetched_at: datetime
    status_code: int


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


async def put(
    conn: aiosqlite.Connection,
    *,
    url: str,
    source: str,
    status_code: int,
    blob_ref: str | None,
    now: datetime | None = None,
) -> None:
    ts = (now or datetime.now(timezone.utc)).isoformat()
    await conn.execute(
        "INSERT OR REPLACE INTO url_cache (url_sha1, url, source, fetched_at, status_code, blob_ref)"
        " VALUES (?,?,?,?,?,?)",
        (_sha1(url), url, source, ts, status_code, blob_ref),
    )
    await conn.commit()


async def get(
    conn: aiosqlite.Connection,
    *,
    url: str,
    now: datetime | None = None,
) -> CacheHit | None:
    cur = await conn.execute(
        "SELECT url, blob_ref, fetched_at, status_code FROM url_cache WHERE url_sha1=?",
        (_sha1(url),),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    fetched_at = datetime.fromisoformat(row[2])
    moment = now or datetime.now(timezone.utc)
    if row[3] != 200:
        return None
    if moment - fetched_at >= _TTL:
        return None
    return CacheHit(url=row[0], blob_ref=row[1], fetched_at=fetched_at, status_code=row[3])
```

- [ ] **Step 4: Run — expect green**

Run: `uv run pytest tests/storage/test_cache.py -v`
Expected: 4 passed.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src/jma/storage/cache.py tests/storage/test_cache.py
git add src/jma/storage/cache.py tests/storage/test_cache.py
git commit -m "feat(storage): URL cache with 24h TTL + injected clock"
```

---

## Task 1.9: Blob storage (spec slice 1.9)

**Files:**
- Create: `src/jma/storage/blobs.py`
- Create: `tests/storage/test_blobs.py`

`write(root, source, url, body, *, now=None) -> str` writes gzipped bytes to `root/raw/{source}/{yyyymmdd}/{sha1(url)[:16]}.html.gz` and returns the path **relative to `root`** (e.g. `"raw/testerhome/20260521/abc123…html.gz"`). `read(root, ref) -> str` decodes.

- [ ] **Step 1: Write failing blob tests (red)**

Create `tests/storage/test_blobs.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from jma.storage.blobs import read, write


def test_write_uses_correct_path_scheme(tmp_path: Path) -> None:
    ref = write(
        root=tmp_path,
        source="testerhome",
        url="https://testerhome.com/jobs?page=1",
        body="<html>hi</html>",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
    )
    assert ref.startswith("raw/testerhome/20260521/")
    assert ref.endswith(".html.gz")
    # Path: 16-char sha1 prefix
    fname = Path(ref).name
    assert len(fname) == len("0123456789abcdef.html.gz")  # 24
    assert (tmp_path / ref).exists()


def test_round_trip(tmp_path: Path) -> None:
    payload = "<html><body>" + ("ABCD" * 1000) + "</body></html>"
    ref = write(root=tmp_path, source="testerhome",
                url="https://x/page", body=payload,
                now=datetime(2026, 5, 21, tzinfo=timezone.utc))
    out = read(root=tmp_path, ref=ref)
    assert out == payload


def test_same_url_same_day_same_path(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, tzinfo=timezone.utc)
    a = write(root=tmp_path, source="testerhome", url="https://x/y", body="a", now=ts)
    b = write(root=tmp_path, source="testerhome", url="https://x/y", body="b", now=ts)
    assert a == b  # path is deterministic
    # body 'b' overwrote 'a'
    assert read(root=tmp_path, ref=a) == "b"
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/storage/test_blobs.py -v`
Expected: fail.

- [ ] **Step 3: Implement `storage/blobs.py` (green)**

Create `src/jma/storage/blobs.py`:

```python
"""Gzipped raw-HTML blobs at data/raw/{source}/{yyyymmdd}/{sha1(url)[:16]}.html.gz."""
from __future__ import annotations

import gzip
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def _sha1_short(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _ref(source: str, url: str, when: datetime) -> str:
    ymd = when.astimezone(timezone.utc).strftime("%Y%m%d")
    return f"raw/{source}/{ymd}/{_sha1_short(url)}.html.gz"


def write(
    *,
    root: str | Path,
    source: str,
    url: str,
    body: str,
    now: datetime | None = None,
) -> str:
    when = now or datetime.now(timezone.utc)
    ref = _ref(source, url, when)
    full = Path(root) / ref
    full.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(full, "wb") as f:
        f.write(body.encode("utf-8"))
    return ref


def read(*, root: str | Path, ref: str) -> str:
    full = Path(root) / ref
    with gzip.open(full, "rb") as f:
        return f.read().decode("utf-8")
```

- [ ] **Step 4: Run — expect green**

Run: `uv run pytest tests/storage/test_blobs.py -v`
Expected: 3 passed.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src/jma/storage/blobs.py tests/storage/test_blobs.py
git add src/jma/storage/blobs.py tests/storage/test_blobs.py
git commit -m "feat(storage): gzipped blob writer/reader with date-sharded paths"
```

---

## Task 1.10: TesterHome source (spec slice 1.10)

**Files:**
- Create: `tests/fixtures/sources/testerhome/listing_ok.html`
- Create: `tests/fixtures/sources/testerhome/listing_empty.html`
- Create: `src/jma/sources/testerhome.py`
- Create: `tests/sources/test_testerhome.py`

This is the biggest slice. We implement the §7.3 algorithm in pieces.

### 1.10a: Fixture HTML

The fixtures must match the YAML selectors:
- `list_item_selector: ".topics .topic"`
- `title_selector: ".title a"` (href + text)
- `posted_at_attr: ".time@title"` (timestamp in the `title` attribute of `.time`)

We define three synthetic topics per page so region+keyword filters exercise multiple branches.

- [ ] **Step 1: Create `listing_ok.html`**

Create `tests/fixtures/sources/testerhome/listing_ok.html`:

```html
<!doctype html>
<html><body>
<div class="topics">
  <div class="topic">
    <div class="title"><a href="/topics/100">【杭州·余杭】AI Agent Engineer 15-30K·14薪</a></div>
    <span class="time" title="2026-05-20T08:00:00+00:00">May 20</span>
  </div>
  <div class="topic">
    <div class="title"><a href="/topics/101">【北京】Senior Backend 20-40K</a></div>
    <span class="time" title="2026-05-19T08:00:00+00:00">May 19</span>
  </div>
  <div class="topic">
    <div class="title"><a href="/topics/102">【杭州】AI agent platform engineer 25-45K·15薪</a></div>
    <span class="time" title="2026-05-18T08:00:00+00:00">May 18</span>
  </div>
</div>
</body></html>
```

- [ ] **Step 2: Create `listing_empty.html`**

Create `tests/fixtures/sources/testerhome/listing_empty.html`:

```html
<!doctype html>
<html><body>
<div class="topics">
  <!-- no .topic elements -->
</div>
</body></html>
```

### 1.10b: Tests (red)

- [ ] **Step 3: Write failing TesterHome tests**

Create `tests/sources/test_testerhome.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(encoding="utf-8")


def _make_source(tmp_path: Path, ac: httpx.AsyncClient) -> TesterHomeSource:
    cfg = load_source_config(CFG_PATH)
    async def _no_sleep(_seconds: float) -> None:  # speed up backoff in tests
        return None
    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
    return TesterHomeSource(
        cfg=cfg,
        http=http,
        data_root=tmp_path,
        sleep=_no_sleep,  # also no inter-page delay
    )


@respx.mock
@pytest.mark.asyncio
async def test_listing_ok_extracts_three_items_no_region_no_kw_filter(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        # region="" disables region filter (kept items must equal empty region == always true via substring)
        result = await src.crawl(region="", keywords=("",), max_pages=1, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert len(result.jobs) == 3
    titles = [j.title_raw for j in result.jobs]
    assert any("AI Agent Engineer" in t for t in titles)
    # Salary parsed for items 1 and 3.
    assert any(j.salary.parsed for j in result.jobs)
    # Page-1 blob ref shared across items on the page.
    refs = {j.raw_payload_ref for j in result.jobs}
    assert len(refs) == 1


@respx.mock
@pytest.mark.asyncio
async def test_region_filter_drops_non_matching_city(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=100)
    cities = [j.location.city for j in result.jobs]
    assert "Beijing" not in cities
    assert "Hangzhou" in cities


@respx.mock
@pytest.mark.asyncio
async def test_keyword_filter_phrase_semantics(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        # "AI agent" matches the literal substring in items 1 and 3.
        result = await src.crawl(region="", keywords=("AI agent",), max_pages=1, max_jobs=100)
    titles = [j.title_raw.lower() for j in result.jobs]
    assert all("ai agent" in t for t in titles)
    assert len(result.jobs) == 2


@respx.mock
@pytest.mark.asyncio
async def test_empty_listing_on_page_1_returns_empty(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.EMPTY
    assert result.jobs == ()


@respx.mock
@pytest.mark.asyncio
async def test_empty_listing_on_page_N_returns_ok_with_collected(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert "end of listing" in result.reason
    assert len(result.jobs) == 3


@respx.mock
@pytest.mark.asyncio
async def test_partial_harvest_on_429_after_page_1(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"}, text="")
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert result.reason.startswith("partial:")
    assert "page 2" in result.reason
    assert len(result.jobs) == 3


@respx.mock
@pytest.mark.asyncio
async def test_hard_block_on_page_1_returns_block_status(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(403, text="forbid")
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=2, max_jobs=100)
    assert result.status == SourceStatus.BLOCKED
    assert result.jobs == ()


@respx.mock
@pytest.mark.asyncio
async def test_max_jobs_truncates_exactly(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=2, max_jobs=2)
    assert len(result.jobs) == 2
    assert result.reason == "max_jobs reached"
```

- [ ] **Step 4: Run — expect ImportError**

Run: `uv run pytest tests/sources/test_testerhome.py -v`
Expected: fail (no module).

### 1.10c: Implementation (green)

- [ ] **Step 5: Implement `sources/testerhome.py`**

Create `src/jma/sources/testerhome.py`:

```python
"""TesterHomeSource — listing-page crawl (spec §7.3)."""
from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from jma.domain.blockage import classify
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
)
from jma.domain.normalize import (
    normalize_for_match,
    parse_experience,
    parse_location,
    parse_salary,
)
from jma.sources.base import SourceConfig
from jma.sources.http import AsyncHttpClient
from jma.storage import blobs

# Salary tokens we strip out of `title_raw` to derive `title`.
_RE_SALARY_TOKENS = re.compile(
    r"(\d+\s*[Kk]?\s*[-–]\s*\d+\s*[Kk](?:\s*·\s*\d+\s*薪)?"
    r"|年薪\s*\d+\s*[-–]\s*\d+\s*万"
    r"|\$\s*\d+\s*K\s*[-–]\s*\$?\s*\d+\s*K"
    r"|日薪\s*\d+(?:\s*[-–]\s*\d+)?"
    r"|时薪\s*\d+(?:\s*[-–]\s*\d+)?)"
)
_RE_TOPIC_ID = re.compile(r"/topics/(\d+)")


_SleepFn = Callable[[float], Awaitable[None]]


class TesterHomeSource:
    name = "testerhome"

    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        sleep: _SleepFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._sleep: _SleepFn = sleep or asyncio.sleep

    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult:
        collected: list[Job] = []
        pages_fetched = 0
        for n in range(1, max_pages + 1):
            url = self._cfg.listing.url_template.format(
                base_url=self._cfg.base_url, page=n
            )
            fetched = await self._http.fetch(url)
            pages_fetched = n
            # Write blob for every fetch (cache integration lives at the pipeline layer in slice 1.11).
            blob_ref = blobs.write(
                root=self._root, source=self.name, url=url, body=fetched.body,
            )

            block = classify(
                status_code=fetched.status_code,
                headers=fetched.headers,
                body_text=fetched.body,
                cfg=self._cfg,
            )
            if block.kind is not SourceStatus.OK:
                if collected:
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.OK,
                        jobs=tuple(collected),
                        reason=f"partial: stopped at page {n} ({block.kind.value}: {block.reason})",
                        pages_fetched=pages_fetched,
                    )
                return SourceResult(
                    source=self.name,
                    status=block.kind,
                    jobs=(),
                    reason=block.reason,
                    pages_fetched=pages_fetched,
                )

            items = _parse_listing(fetched.body, self._cfg)
            if not items:
                if collected:
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.OK,
                        jobs=tuple(collected),
                        reason=f"end of listing at page {n}",
                        pages_fetched=pages_fetched,
                    )
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.EMPTY,
                    jobs=(),
                    reason=f"0 items at {self._cfg.known_good_list_selector!r} on page 1",
                    pages_fetched=pages_fetched,
                )

            page_jobs = [
                _item_to_job(item, cfg=self._cfg, source_name=self.name,
                             blob_ref=blob_ref)
                for item in items
            ]
            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)
            collected.extend(page_jobs)

            if len(collected) >= max_jobs:
                collected = collected[:max_jobs]
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason="max_jobs reached",
                    pages_fetched=pages_fetched,
                )

            if n == max_pages:
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason="max_pages reached",
                    pages_fetched=pages_fetched,
                )

            await self._sleep(self._cfg.rate.delay_ms / 1000.0)

        # Unreachable in practice; defensive default.
        return SourceResult(
            source=self.name, status=SourceStatus.OK, jobs=tuple(collected),
            pages_fetched=pages_fetched,
        )


# -- pure helpers --------------------------------------------------------


def _parse_listing(body: str, cfg: SourceConfig) -> list[dict]:
    tree = HTMLParser(body)
    selector = cfg.listing.list_item_selector
    items: list[dict] = []
    for node in tree.css(selector):
        anchor = node.css_first(cfg.listing.title_selector)
        if anchor is None:
            continue
        href = anchor.attributes.get(cfg.listing.href_attr) or ""
        title_text = (anchor.text() or "").strip()
        # posted_at_attr is e.g. ".time@title" — split.
        selector_part, _, attr = cfg.listing.posted_at_attr.partition("@")
        posted_at = ""
        time_node = node.css_first(selector_part)
        if time_node is not None:
            posted_at = time_node.attributes.get(attr) or ""
        items.append({"title": title_text, "href": href, "posted_at_attr": posted_at})
    return items


def _strip_salary_tokens(title_raw: str) -> str:
    out = _RE_SALARY_TOKENS.sub("", title_raw)
    return re.sub(r"\s+", " ", out).strip()


def _extract_salary_token(title_raw: str) -> str:
    m = _RE_SALARY_TOKENS.search(title_raw)
    return m.group(0) if m else ""


def _item_to_job(item: dict, *, cfg: SourceConfig, source_name: str, blob_ref: str) -> Job:
    title_raw = item["title"]
    href = item["href"]
    posted_at_attr = item["posted_at_attr"]

    title = _strip_salary_tokens(title_raw)
    salary = parse_salary(_extract_salary_token(title_raw))
    location = parse_location(title_raw)
    experience = parse_experience(title_raw)

    m = _RE_TOPIC_ID.search(href)
    internal_id = m.group(1) if m else None

    url = urljoin(cfg.base_url, href)

    posted_at = None
    if posted_at_attr:
        try:
            posted_at = datetime.fromisoformat(posted_at_attr)
        except ValueError:
            posted_at = None

    company = None  # listing page doesn't expose company

    return Job(
        id=job_id(source=source_name, internal_id=internal_id,
                  title=title, company=company, city=location.city),
        canonical_id=canonical_id(title=title, company=company, city=location.city),
        source=source_name,
        source_internal_id=internal_id,
        title=title,
        title_raw=title_raw,
        company=company,
        location=location,
        salary=salary,
        experience=experience,
        posted_at=posted_at,
        fetched_at=datetime.now(timezone.utc),
        url=url,
        raw_payload_ref=blob_ref,
    )


def _filter_region(jobs: list[Job], region: str) -> list[Job]:
    if region == "":
        return jobs
    needle = normalize_for_match(region)
    kept: list[Job] = []
    for j in jobs:
        city = j.location.city
        if city is None or city == "":
            kept.append(j)  # keep observations with unparseable city
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
```

- [ ] **Step 6: Run TesterHome tests — expect green**

Run: `uv run pytest tests/sources/test_testerhome.py -v`
Expected: 8 passed.

If any test fails: read the spec §7.3 step number that the failing assertion targets; do not mutate the algorithm — fix the implementation to match the spec.

- [ ] **Step 7: Refactor — verify pure helpers are stateless**

Read `_parse_listing`, `_strip_salary_tokens`, `_extract_salary_token`, `_filter_region`, `_filter_keywords`. None should reach into `self`. They don't — leave as-is.

- [ ] **Step 8: Ruff + commit**

```bash
uv run ruff check src/jma/sources/testerhome.py tests/sources/test_testerhome.py tests/fixtures/
git add src/jma/sources/testerhome.py tests/sources/test_testerhome.py tests/fixtures/sources/testerhome/
git commit -m "feat(sources): TesterHomeSource crawl + region/keyword filters + PartialHarvest"
```

---

## Task 1.11: Crawl pipeline (spec slice 1.11)

**Files:**
- Create: `src/jma/pipeline/crawl.py`
- Create: `tests/pipeline/test_crawl_e2e.py`

`pipeline.crawl.run(*, region, keywords, source_factory, db_path, data_root, max_pages, max_jobs, use_cache) -> tuple[str, list[SourceResult]]` glues the source loop to storage. It opens the DB, starts a Run, calls `source.crawl(...)`, persists Jobs + `run_jobs` edges + the URL cache, and finishes the Run.

For Phase 1 the source factory yields a single source (TesterHome). `source_factory` is `(http_client) -> JobSource` so the pipeline owns the `httpx.AsyncClient` lifecycle.

Cache integration: the pipeline asks the source's HTTP client to use the cache via a thin wrapper. To keep the slice surgical, we wire cache **inside the pipeline**, not inside `TesterHomeSource`: the pipeline pre-populates the cache after each fetch by reading `url_cache` and writing `blob_ref` based on the blob the source already wrote. Because slice 1.10's source writes a blob per fetch, the pipeline merely needs to record those writes by intercepting via a callback.

Concrete design: the pipeline passes an `on_fetch(url, status_code, blob_ref)` callback into the source. We add this hook to `TesterHomeSource` in this slice. Backward-compatible: if `on_fetch=None`, the source does nothing extra.

- [ ] **Step 1: Add `on_fetch` hook to `TesterHomeSource` (refactor: small, behaviour-preserving)**

Edit `src/jma/sources/testerhome.py`:

Update `__init__` signature to accept an optional `on_fetch`:

Replace:
```python
    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        sleep: _SleepFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._sleep: _SleepFn = sleep or asyncio.sleep
```

With:
```python
    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        sleep: _SleepFn | None = None,
        on_fetch: Callable[[str, int, str], Awaitable[None]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._sleep: _SleepFn = sleep or asyncio.sleep
        self._on_fetch = on_fetch
```

Then in the `crawl` loop, immediately after `blob_ref = blobs.write(...)`, add:

```python
            if self._on_fetch is not None:
                await self._on_fetch(url, fetched.status_code, blob_ref)
```

Run the TesterHome test set again to confirm we haven't regressed.

Run: `uv run pytest tests/sources/test_testerhome.py -v`
Expected: still 8 passed.

- [ ] **Step 2: Write failing pipeline e2e test (red)**

Create `tests/pipeline/test_crawl_e2e.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from jma.pipeline.crawl import run
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(encoding="utf-8")


def _factory(tmp_path: Path):
    async def _no_sleep(_s: float) -> None: return None
    cfg = load_source_config(CFG_PATH)

    def _make(ac: httpx.AsyncClient, on_fetch):
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        return TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path,
                                sleep=_no_sleep, on_fetch=on_fetch)
    return _make


@respx.mock
@pytest.mark.asyncio
async def test_end_to_end_writes_runs_jobs_run_jobs_cache_blob(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )

    run_id, source_results = await run(
        region="Hangzhou",
        keywords=("AI agent",),
        source_factory=_factory(tmp_path),
        db_path=tmp_path / "data/jobs.db",
        data_root=tmp_path,
        max_pages=3,
        max_jobs=100,
        use_cache=True,
    )

    assert isinstance(run_id, str) and len(run_id) == 32
    assert len(source_results) == 1
    assert source_results[0].status.value == "ok"
    assert len(source_results[0].jobs) >= 1

    # DB invariants.
    import aiosqlite
    async with aiosqlite.connect(str(tmp_path / "data/jobs.db")) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM runs WHERE id=?", (run_id,))
        assert (await cur.fetchone())[0] == 1
        cur = await conn.execute("SELECT COUNT(*) FROM jobs")
        n_jobs = (await cur.fetchone())[0]
        assert n_jobs >= 1
        cur = await conn.execute("SELECT canonical_id FROM jobs LIMIT 1")
        (canon,) = await cur.fetchone()
        assert canon != ""
        cur = await conn.execute("SELECT COUNT(*) FROM run_jobs WHERE run_id=?", (run_id,))
        assert (await cur.fetchone())[0] == n_jobs
        cur = await conn.execute("SELECT COUNT(*) FROM url_cache WHERE status_code=200")
        assert (await cur.fetchone())[0] >= 1

    # Blob present.
    blobs_dir = tmp_path / "raw/testerhome"
    assert blobs_dir.exists()
    assert any(p.suffix == ".gz" for p in blobs_dir.rglob("*"))
```

- [ ] **Step 3: Run — expect ImportError**

Run: `uv run pytest tests/pipeline/test_crawl_e2e.py -v`
Expected: fail.

- [ ] **Step 4: Implement `pipeline/crawl.py` (green)**

Create `src/jma/pipeline/crawl.py`:

```python
"""Crawl orchestration (spec §11 slice 1.11)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from jma.domain.models import SourceResult
from jma.sources.base import JobSource
from jma.storage import cache as urlcache
from jma.storage.db import finish_run, insert_jobs, open_db, start_run


SourceFactory = Callable[
    [httpx.AsyncClient, Callable[[str, int, str], Awaitable[None]]],
    JobSource,
]


async def run(
    *,
    region: str,
    keywords: tuple[str, ...],
    source_factory: SourceFactory,
    db_path: str | Path,
    data_root: str | Path,
    max_pages: int,
    max_jobs: int,
    use_cache: bool,
) -> tuple[str, list[SourceResult]]:
    conn = await open_db(db_path)
    try:
        run_id = await start_run(conn, region=region, keywords=keywords)

        async def on_fetch(url: str, status_code: int, blob_ref: str) -> None:
            await urlcache.put(
                conn,
                url=url,
                source="testerhome",  # single-source slice
                status_code=status_code,
                blob_ref=blob_ref if status_code == 200 else None,
            )

        async with httpx.AsyncClient() as ac:
            source = source_factory(ac, on_fetch if use_cache else _noop)
            t0 = time.perf_counter()
            result = await source.crawl(
                region=region,
                keywords=keywords,
                max_pages=max_pages,
                max_jobs=max_jobs,
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            result = result.model_copy(update={"elapsed_ms": elapsed_ms})

        await insert_jobs(conn, run_id, list(result.jobs))
        await finish_run(conn, run_id=run_id, source_results=[result])
        return run_id, [result]
    finally:
        await conn.close()


async def _noop(url: str, status_code: int, blob_ref: str) -> None:
    return None
```

- [ ] **Step 5: Run — expect green**

Run: `uv run pytest tests/pipeline/test_crawl_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 6: Full suite check**

Run: `uv run pytest -v`
Expected: every test green except live (which is skipped).

- [ ] **Step 7: Ruff + commit**

```bash
uv run ruff check src/jma/pipeline/ tests/pipeline/ src/jma/sources/testerhome.py
git add src/jma/pipeline/crawl.py src/jma/sources/testerhome.py tests/pipeline/test_crawl_e2e.py
git commit -m "feat(pipeline): orchestrate crawl, persist runs+jobs+run_jobs+url_cache"
```

---

## Task 1.12: CLI (spec slice 1.12)

**Files:**
- Create: `src/jma/cli.py`
- Create: `tests/cli/test_cli.py`

`jma crawl` is the only subcommand for Phase 1. We register it on a Typer `app` and expose `app` so `typer.testing.CliRunner` can drive it.

Exit codes (spec §8):
- 0 if any source returned `status=OK` with ≥1 job (includes PartialHarvest).
- 2 if every source returned non-OK or empty-OK.
- 1 on uncaught exception (Typer's default).

- [ ] **Step 1: Write failing CLI tests (red)**

Create `tests/cli/test_cli.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from jma.cli import app

REPO = Path(__file__).resolve().parents[2]
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(encoding="utf-8")


@respx.mock
def test_crawl_success_exit_zero(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "Hangzhou", "--keywords", "AI agent",
         "--max-pages", "3", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "run_id" in result.stdout
    assert "testerhome" in result.stdout
    assert "ok" in result.stdout


@respx.mock
def test_crawl_partial_harvest_still_exit_zero(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"}, text="")
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "", "--keywords", "",
         "--max-pages", "3", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert "partial" in result.stdout


@respx.mock
def test_crawl_all_blocked_exit_two(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(403, text="forbid")
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "Hangzhou", "--keywords", "AI",
         "--max-pages", "1", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 2
    assert "blocked" in result.stdout.lower() or "HTTP 403" in result.stdout


@respx.mock
def test_crawl_empty_listing_exit_two(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "Hangzhou", "--keywords", "AI",
         "--max-pages", "1", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 2


@respx.mock
def test_crawl_multiple_keywords_are_ored(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "", "--keywords", "AI agent", "--keywords", "Senior",
         "--max-pages", "3", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0
    # All three fixture items should be retained: 2 contain "AI agent", 1 contains "Senior".
    assert "jobs=3" in result.stdout
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: fail.

- [ ] **Step 3: Implement `src/jma/cli.py` (green)**

Create `src/jma/cli.py`:

```python
"""`jma` Typer entry-point (spec §8)."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Awaitable, Callable

import httpx
import typer

from jma.domain.models import SourceResult, SourceStatus
from jma.pipeline.crawl import run as pipeline_run
from jma.sources.base import JobSource, load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

app = typer.Typer(add_completion=False, no_args_is_help=True)

_CFG_DIR = Path(__file__).resolve().parents[2] / "config" / "sources"


def _data_root() -> Path:
    env = os.environ.get("JMA_DATA_ROOT")
    if env:
        return Path(env)
    return Path.cwd() / "data"


def _factory_for(source_name: str):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")

    def _make(ac: httpx.AsyncClient, on_fetch: Callable[[str, int, str], Awaitable[None]]) -> JobSource:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        return TesterHomeSource(cfg=cfg, http=http, data_root=_data_root(), on_fetch=on_fetch)

    return _make


def _summary_lines(run_id: str, region: str, keywords: tuple[str, ...],
                   results: list[SourceResult], db_path: Path) -> list[str]:
    lines = [
        f"run_id        : {run_id}",
        f"region        : {region or '(empty)'}",
        f"keywords      : {', '.join(keywords) if keywords else '(empty)'}",
        "sources:",
    ]
    total_obs = 0
    for r in results:
        n = len(r.jobs)
        total_obs += n
        if r.status is SourceStatus.OK:
            line = f"  {r.source:<11}: ok    pages={r.pages_fetched}  jobs={n}   elapsed={r.elapsed_ms/1000:.1f}s"
            if r.reason.startswith("partial:"):
                line += f"  {r.reason}"
            lines.append(line)
        else:
            lines.append(
                f"  {r.source:<11}: {r.status.value}  reason=\"{r.reason}\"  pages={r.pages_fetched}  jobs={n}"
            )
    lines.append(f"written       : {total_obs} observations to {db_path}")
    return lines


def _exit_code(results: list[SourceResult]) -> int:
    for r in results:
        if r.status is SourceStatus.OK and len(r.jobs) >= 1:
            return 0
    return 2


@app.command()
def crawl(
    region: str = typer.Option(..., "--region", help="Region (e.g. Hangzhou). Empty disables region filter."),
    keywords: list[str] = typer.Option(..., "--keywords", help="Repeatable keyword phrase."),
    source: list[str] = typer.Option(["testerhome"], "--source", help="Source name (repeatable)."),
    max_pages: int = typer.Option(5, "--max-pages"),
    max_jobs: int = typer.Option(300, "--max-jobs"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    keywords_t = tuple(keywords)

    async def _run_all() -> tuple[str, list[SourceResult]]:
        all_results: list[SourceResult] = []
        run_id_final: str | None = None
        db_path = _data_root() / "jobs.db"
        for s_name in source:
            run_id, results = await pipeline_run(
                region=region,
                keywords=keywords_t,
                source_factory=_factory_for(s_name),
                db_path=db_path,
                data_root=_data_root(),
                max_pages=max_pages,
                max_jobs=max_jobs,
                use_cache=not no_cache,
            )
            run_id_final = run_id  # Phase 1: one source, single Run is fine
            all_results.extend(results)
        assert run_id_final is not None
        return run_id_final, all_results

    try:
        run_id, results = asyncio.run(_run_all())
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    db_path = _data_root() / "jobs.db"
    for line in _summary_lines(run_id, region, keywords_t, results, db_path):
        typer.echo(line)

    raise typer.Exit(code=_exit_code(results))
```

- [ ] **Step 4: Run CLI tests — expect green**

Run: `uv run pytest tests/cli/test_cli.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -v`
Expected: every non-live test green. Count: roughly 50+ tests.

- [ ] **Step 6: Ruff + commit**

```bash
uv run ruff check src/jma/cli.py tests/cli/test_cli.py
git add src/jma/cli.py tests/cli/test_cli.py
git commit -m "feat(cli): jma crawl with stdout summary and PartialHarvest-aware exit codes"
```

---

## Task 1.13: Live smoke test + manual smoke (spec slice 1.13)

**Files:**
- Create: `tests/live/test_testerhome_live.py`

The live test is marked `@pytest.mark.live` and skipped by default (pyproject's `addopts = "-m 'not live'"`). It hits the real site once. CI does not run it; the maintainer runs it manually before declaring the phase done.

- [ ] **Step 1: Create the live test**

Create `tests/live/test_testerhome_live.py`:

```python
from pathlib import Path

import httpx
import pytest

from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"


@pytest.mark.live
@pytest.mark.asyncio
async def test_testerhome_live_smoke(tmp_path: Path) -> None:
    cfg = load_source_config(CFG_PATH)
    async with httpx.AsyncClient(
        headers={"User-Agent": "jma-live-smoke/0.1 (+https://github.com/snowshine0216/job-market-agent)"},
        timeout=30.0,
    ) as ac:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        src = TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path)
        result = await src.crawl(region="", keywords=("",), max_pages=1, max_jobs=50)

    assert result.status.value == "ok", f"unexpected status: {result.status} ({result.reason})"
    assert len(result.jobs) >= 1, "expected at least one job from live TesterHome listing page 1"
```

- [ ] **Step 2: Confirm it is skipped by default**

Run: `uv run pytest -v`
Expected: live test is **not** collected (or collected and skipped, depending on pytest-asyncio integration). No new failures.

- [ ] **Step 3: Document the manual smoke command (do not run)**

The manual command per spec §10 (the engineer runs this on their own machine before declaring the phase done):

```bash
uv run pytest -m live -v          # optional, runs against real testerhome.com
uv run jma crawl --region Hangzhou --keywords "AI agent"
```

Expected on success: stdout shows a `run_id`, at least one `testerhome  : ok ...` line with `jobs >= 1`, a blob under `data/raw/testerhome/<yyyymmdd>/`, and rows in `data/jobs.db`.

- [ ] **Step 4: Final full suite + ruff**

Run:
```bash
uv run pytest -v
uv run ruff check .
```
Expected: all non-live tests green; ruff clean.

- [ ] **Step 5: Commit slice 1.13**

```bash
git add tests/live/test_testerhome_live.py
git commit -m "test(live): opt-in TesterHome smoke (@pytest.mark.live)"
```

---

## Phase exit checklist (spec §10)

- [ ] `uv run pytest` exits 0 with the live marker skipped.
- [ ] `uv run pytest -m live` green on the maintainer's machine (out-of-band, not in CI).
- [ ] Manual smoke: `uv run jma crawl --region Hangzhou --keywords "AI agent"` produces a `runs` row, ≥1 `jobs` row with non-empty `canonical_id`, matching `run_jobs` edge, gzipped blob under `data/raw/testerhome/<yyyymmdd>/`.
- [ ] `uv run ruff check .` clean.

---

## Spec-coverage cross-reference

| Spec section | Plan task(s) |
|---|---|
| §1 In scope | Tasks 0.1 … 1.13 (full slice list below) |
| §2 Decision table rows 1–15 | Models (0.2), normalize (1.1, 1.2), dedup (1.3), blockage (1.4), source config (1.5), http (1.6), db schema (1.7), cache (1.8), blobs (1.9), TesterHome (1.10), pipeline (1.11), CLI (1.12) |
| §3 Module layout | "File Structure" block above; every file path in this plan matches |
| §4 Data models | Task 0.2 verbatim |
| §5 SQLite DDL | Task 1.7 inlines the DDL |
| §6 Blockage classifier | Task 1.4 inlines decision tree + `snippet_around` |
| §7.1 testerhome.yaml | Task 1.5 inlines YAML |
| §7.2 JobSource Protocol | Task 1.5 |
| §7.3 Algorithm steps 1–12 | Task 1.10 inlines per-page loop matching steps 1–12 |
| §8 CLI surface | Task 1.12 wires options + exit codes |
| §9 Testing strategy | Test files map row-by-row to plan tasks |
| §10 Exit criteria | "Phase exit checklist" above |
| §11 Slice order | Tasks 0.1 → 1.13 follow it 1:1 |
| §12 Risks | Mitigations live in: (a) two-source `canonical_id` round-trip test in Task 1.7; (b) fixture HTML + live smoke in Tasks 1.10 + 1.13; (c) salary corpus expansion in Task 1.1; (d) PartialHarvest tested in Task 1.10 and surfaced in CLI test in Task 1.12 |

## Judgment calls embedded in this plan

These are not in the spec verbatim — they're choices this plan locks in so the implementer doesn't have to:

1. **Python 3.12 minimum** — `requires-python = ">=3.12"`. Spec doesn't pin; we pick 3.12 for clean `str | None` typing and `match` if needed.
2. **`uv` workflow** — `uv add` for deps, `uv lock` after, `uv run` for invocations. Spec only says "via `uv`" (§1).
3. **`[tool.ruff]` in pyproject** — not a separate `ruff.toml`. Spec offers both; we choose one to avoid duplication.
4. **Live marker registered + `addopts = "-m 'not live'"`** — spec §9 mentions both; we wire them in pyproject explicitly.
5. **Salary corpus (12 rows)** — spec §1 references "PLAN case 1.A corpus" but PLAN.md is out of scope. The 12-row corpus in Task 1.1 covers monthly, annual (CNY + USD), unparseable, empty, NFKC width variants, whitespace variants, daily, hourly. DAILY/HOURLY set `parsed=True` with `min/max=None` per spec §2 row 11.
6. **City pinyin map** — 11 entries cover the cities most likely to appear in Phase 1 TesterHome listings. Unknown native city → `district=<native>`, `city=None`. Spec doesn't enumerate; this lives in `normalize.py` and is easy to extend.
7. **`normalize_for_match` exposed publicly** — spec implies dedup shares the normaliser; we add a public alias so `dedup.py` and `testerhome.py` filters consume the same function.
8. **HTTP retry policy** — retry on 429 + 5xx only, do not retry 401/403. Spec §6 classifier separates BLOCKED (401/403) from RATE_LIMITED (429); the HTTP layer mirrors that — 403 is a real block, not transient.
9. **Cache wiring lives in `pipeline.crawl`, not in `TesterHomeSource`** — keeps the source pure-of-DB. The source emits an `on_fetch(url, status, blob_ref)` callback; the pipeline pipes it into `storage.cache.put`.
10. **`elapsed_ms`** — measured by the pipeline (`time.perf_counter()`), patched onto the source's `SourceResult` via `model_copy(update=...)`. Frozen-friendly.
11. **CLI `JMA_DATA_ROOT` env var** — lets the CLI tests redirect data into `tmp_path`. Not exposed in user docs (deferred); it just makes testing tractable.
12. **CLI `--region` and `--keywords` are required** (per spec §8 wording: "required, single string" / "required, repeatable"). Empty strings are explicitly allowed by the source-level filters (region="" disables; keywords=("",) disables).

## Self-review notes

- All code blocks contain real implementations — no `TODO` / `...` / "implement later".
- Every TDD slice writes the failing test first, then the minimum impl, then a refactor consideration (skipped where the minimum impl is already clean).
- Type names used downstream (`SourceConfig`, `RateConfig`, `AsyncHttpClient`, `FetchResult`, `Job`, `SourceResult`, `BlockStatus`, `TesterHomeSource`, `CacheHit`) are all defined in earlier slices.
- Function signatures stay stable across slices — e.g. `job_id(...)` and `canonical_id(...)` are used in Task 1.7 with the exact keyword-only signature defined in Task 1.3.

---

*End of plan.*
