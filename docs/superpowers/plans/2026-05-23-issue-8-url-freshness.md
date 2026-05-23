# Issue #8 — URL freshness (`url_status`, `url_last_checked_at`, durable-signal model)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stale TesterHome job URLs detectable in the database. Add two columns (`url_status`, `url_last_checked_at`) to the `jobs` table, populate them from the detail-fetch path introduced in issue #7, and surface a `gone_urls=N` count in the `jma crawl` summary. `url_status` is the **durable best-known truth** about whether the URL still resolves — transient outcomes never erase prior signal. `data_quality` is intentionally **not** touched by URL freshness (see [ADR 0003](../../adr/0003-url-freshness-as-durable-signal.md)).

**Architecture:** Additive schema change with an idempotent ALTER-TABLE migration. Two new fields on the `Job` pydantic model — `url_status: UrlStatus` (a new `StrEnum` with `LIVE / GONE / UNKNOWN`, consistent with `WorkMode` / `Seniority` / etc.) and `url_last_checked_at: datetime | None`. Freshness is computed inside `TesterHomeSource._enrich_page` via a new pure helper `_apply_url_freshness(job, *, status_code, checked_at)` that maps definitive outcomes (`200 → live`, `404/410 → gone`) and leaves transient ones (3xx, 429, other 4xx, 5xx, network errors) untouched. Persistence switches `_INSERT_JOB` from `INSERT OR REPLACE` to `INSERT … ON CONFLICT(id) DO UPDATE SET …`, with a narrow conditional clause on the two freshness columns so a transient re-crawl can never overwrite a previously earned `live`/`gone` signal. The CLI counts `url_status == GONE` in the run's `result.jobs` and **omits** the `gone_urls=N` segment when no Job in the run has a `url_last_checked_at` (i.e. listing-only crawl).

**Tech Stack:** Python 3.12, aiosqlite, pydantic v2 frozen models, pytest. Tests via `uv run pytest`.

**Issue link:** [snowshine0216/job-market-agent#8](https://github.com/snowshine0216/job-market-agent/issues/8)

**Related ADR:** [docs/adr/0003-url-freshness-as-durable-signal.md](../../adr/0003-url-freshness-as-durable-signal.md) — records the durable-signal semantic, the decoupling from `data_quality`, and the rejected alternatives.

**Depends on:** [issue #7 plan](./2026-05-23-issue-7-detail-page-fetch.md). The detail-fetch loop must exist before freshness can be wired into it. If executing issues #7 and #8 in the same branch, complete #7 Task 5 (the `_enrich_page` loop) before starting this plan.

---

## File Structure

- Modify: [src/jma/domain/models.py](../../../src/jma/domain/models.py)
  - Add `class UrlStatus(StrEnum)` with `LIVE / GONE / UNKNOWN`, alongside the other StrEnums.
  - Add two new fields on `Job`: `url_status: UrlStatus = UrlStatus.UNKNOWN`, `url_last_checked_at: datetime | None = None`.

- Modify: [src/jma/storage/db.py](../../../src/jma/storage/db.py)
  - Add `url_status` and `url_last_checked_at` columns to the `jobs` CREATE TABLE (for new DBs).
  - Add an idempotent migration step in `open_db` that runs `ALTER TABLE jobs ADD COLUMN …` and swallows the `OperationalError` raised when columns already exist.
  - Replace `_INSERT_JOB` with an `ON CONFLICT(id) DO UPDATE SET …` upsert. All existing columns use `excluded.X` (latest-wins, same as before). The two freshness columns use a `CASE WHEN excluded.url_status IN ('live','gone') THEN excluded.X ELSE jobs.X END` clause so transient outcomes never overwrite earned signal.
  - Update `_job_to_row` to include the two new columns.

- Modify: [src/jma/sources/testerhome.py](../../../src/jma/sources/testerhome.py)
  - Add pure helper `_apply_url_freshness(job, *, status_code, checked_at) -> Job`.
  - Call it from `_enrich_page` for each detail-fetch outcome.

- Modify: [src/jma/cli.py](../../../src/jma/cli.py)
  - In `_summary_lines`, when any Job in `result.jobs` has `url_last_checked_at is not None`, count `j.url_status == UrlStatus.GONE` and append a `gone_urls=N` segment to the source line. When no Job has `url_last_checked_at`, omit the segment entirely (signals "we didn't check," not "checked and found none").

- Modify: [CONTEXT.md](../../../CONTEXT.md)
  - Add a `## URL freshness` glossary section explaining the three `url_status` values and the durable-signal semantic. Do **not** introduce a `data_quality` entry — this issue does not touch `data_quality`.

- New test files:
  - `tests/storage/test_db_migration.py` — verifies an old-schema DB gains the columns AND that the upsert preserves earned freshness signal on transient re-insert.
  - `tests/sources/test_url_freshness.py` — unit tests for `_apply_url_freshness`.
  - Integration assertion added to existing `tests/sources/test_testerhome_with_detail.py` (from #7's plan).

---

## Tasks

### Task 1: Extend `Job` model with freshness fields

**Files:**
- Modify: `src/jma/domain/models.py`

- [ ] **Step 1: Write a failing test for the new fields and defaults**

Create `tests/domain/test_models_url_freshness.py`:

```python
from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus


def _minimal_job() -> Job:
    return Job(
        id=job_id(source="testerhome", internal_id="1", title="t",
                  company=None, city=None),
        canonical_id=canonical_id(title="t", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime.now(UTC),
        url="https://x/",
        raw_payload_ref="x.gz",
    )


def test_job_defaults_url_status_to_unknown_and_no_check_time() -> None:
    j = _minimal_job()
    assert j.url_status is UrlStatus.UNKNOWN
    assert j.url_last_checked_at is None


def test_job_accepts_all_url_status_values() -> None:
    base = _minimal_job()
    now = datetime.now(UTC)
    for status in (UrlStatus.LIVE, UrlStatus.GONE, UrlStatus.UNKNOWN):
        upd = base.model_copy(update={"url_status": status, "url_last_checked_at": now})
        assert upd.url_status is status
        assert upd.url_last_checked_at == now


def test_url_status_serialises_as_string_value() -> None:
    assert UrlStatus.LIVE.value == "live"
    assert UrlStatus.GONE.value == "gone"
    assert UrlStatus.UNKNOWN.value == "unknown"
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/domain/test_models_url_freshness.py -v`

Expected: FAIL — `UrlStatus` and the new fields don't exist yet.

- [ ] **Step 3: Add `UrlStatus` and the new fields in `src/jma/domain/models.py`**

In `src/jma/domain/models.py`, add `UrlStatus` next to the other StrEnums (after `SourceStatus`):

```python
class UrlStatus(StrEnum):
    LIVE = "live"
    GONE = "gone"
    UNKNOWN = "unknown"
```

Then append two new fields to the `Job` class (the `data_quality: float = 1.0` line is the last current field):

```python
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
    url_status: UrlStatus = UrlStatus.UNKNOWN
    url_last_checked_at: datetime | None = None
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `uv run pytest tests/domain/test_models_url_freshness.py -v`

Expected: 3 passed.

- [ ] **Step 5: Run the whole domain suite — nothing else should change**

Run: `uv run pytest tests/domain -v`

Expected: all green; the new field defaults are backwards-compatible.

- [ ] **Step 6: Commit**

```bash
git add src/jma/domain/models.py tests/domain/test_models_url_freshness.py
git commit -m "feat(domain): UrlStatus + url_last_checked_at on Job (#8)"
```

---

### Task 2: DB schema + idempotent ALTER-TABLE migration

**Files:**
- Modify: `src/jma/storage/db.py`
- Create: `tests/storage/test_db_migration.py`

- [ ] **Step 1: Write a failing migration test**

Create `tests/storage/test_db_migration.py`:

```python
from pathlib import Path

import aiosqlite
import pytest

from jma.storage.db import open_db

# A schema snapshot from before the url_status migration.
_OLD_DDL = """
CREATE TABLE jobs (
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
"""


@pytest.mark.asyncio
async def test_open_db_migrates_old_jobs_table(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    conn = await aiosqlite.connect(str(db_path))
    await conn.executescript(_OLD_DDL)
    await conn.commit()
    await conn.close()

    ctx = await open_db(db_path)
    async with ctx as db:
        cur = await db.execute("PRAGMA table_info(jobs)")
        cols = {row[1] for row in await cur.fetchall()}
    assert "url_status" in cols
    assert "url_last_checked_at" in cols


@pytest.mark.asyncio
async def test_open_db_is_idempotent_on_already_migrated_db(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    # First open creates with new schema.
    ctx1 = await open_db(db_path)
    async with ctx1 as db:
        await db.execute("SELECT 1")
    # Second open must not raise.
    ctx2 = await open_db(db_path)
    async with ctx2 as db:
        await db.execute("SELECT 1")
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `uv run pytest tests/storage/test_db_migration.py -v`

Expected: FAIL — `url_status` column missing on the old DB.

- [ ] **Step 3: Update `_DDL` and add the migration function in `src/jma/storage/db.py`**

In the `_DDL` `jobs` CREATE TABLE, replace:

```python
    raw_payload_ref          TEXT NOT NULL,
    data_quality             REAL NOT NULL DEFAULT 1.0
);
```

with:

```python
    raw_payload_ref          TEXT NOT NULL,
    data_quality             REAL NOT NULL DEFAULT 1.0,
    url_status               TEXT NOT NULL DEFAULT 'unknown',
    url_last_checked_at      TEXT
);
```

Then add a migration helper above `open_db`:

```python
_JOBS_MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE jobs ADD COLUMN url_status TEXT NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE jobs ADD COLUMN url_last_checked_at TEXT",
)


async def _apply_jobs_migrations(conn: aiosqlite.Connection) -> None:
    """Idempotent column additions for existing DBs. SQLite has no
    IF NOT EXISTS for ALTER TABLE ADD COLUMN, so we swallow the
    duplicate-column error."""
    import sqlite3
    for stmt in _JOBS_MIGRATIONS:
        try:
            await conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
    await conn.commit()
```

Update `open_db` (currently around line 102) from:

```python
async def open_db(path: str | Path) -> _DbContext:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(p))
    await conn.executescript(_DDL)
    return _DbContext(conn)
```

to:

```python
async def open_db(path: str | Path) -> _DbContext:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(p))
    await conn.executescript(_DDL)
    await _apply_jobs_migrations(conn)
    return _DbContext(conn)
```

- [ ] **Step 4: Run the migration test to confirm both cases pass**

Run: `uv run pytest tests/storage/test_db_migration.py -v`

Expected: 2 passed.

- [ ] **Step 5: Run the full storage suite**

Run: `uv run pytest tests/storage -v`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/jma/storage/db.py tests/storage/test_db_migration.py
git commit -m "feat(storage): jobs.url_status + url_last_checked_at with idempotent migration (#8)"
```

---

### Task 3: Conditional upsert preserving earned freshness signal

**Files:**
- Modify: `src/jma/storage/db.py`
- Modify: `tests/storage/test_db_migration.py`

Switch from `INSERT OR REPLACE` to `INSERT … ON CONFLICT(id) DO UPDATE`, with a narrow conditional clause on the two freshness columns so a transient re-crawl can never overwrite a previously earned `live`/`gone` signal. All other columns retain latest-wins semantics — see [ADR 0003](../../adr/0003-url-freshness-as-durable-signal.md) for the scope decision and the deferred broader merge policy.

- [ ] **Step 1: Write failing round-trip + upsert-preservation tests**

Append to `tests/storage/test_db_migration.py`:

```python
from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus
from jma.storage.db import insert_jobs, start_run


def _job(**overrides) -> Job:
    base = dict(
        id=job_id(source="testerhome", internal_id="9", title="t",
                  company=None, city=None),
        canonical_id=canonical_id(title="t", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        url="https://x/",
        raw_payload_ref="x.gz",
    )
    base.update(overrides)
    return Job(**base)


@pytest.mark.asyncio
async def test_insert_round_trips_url_status_and_check_time(tmp_path: Path) -> None:
    db_path = tmp_path / "rt.db"
    checked_at = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    j = _job(url_status=UrlStatus.GONE, url_last_checked_at=checked_at)

    ctx = await open_db(db_path)
    async with ctx as db:
        run_id = await start_run(db, region="", keywords=())
        await insert_jobs(db, run_id, [j])
        cur = await db.execute(
            "SELECT url_status, url_last_checked_at FROM jobs WHERE id=?",
            (j.id,),
        )
        row = await cur.fetchone()

    assert row[0] == "gone"
    assert row[1] == checked_at.isoformat()


@pytest.mark.asyncio
async def test_upsert_preserves_earned_freshness_on_listing_only_recrawl(
    tmp_path: Path,
) -> None:
    """Day 1: detail-fetch establishes url_status=live. Day 2: listing-only
    re-crawl re-inserts the Job with default url_status=unknown. The
    earned 'live' signal MUST be preserved."""
    db_path = tmp_path / "preserve.db"
    t1 = datetime(2026, 5, 23, tzinfo=UTC)

    day1 = _job(url_status=UrlStatus.LIVE, url_last_checked_at=t1)
    day2 = _job()  # defaults: url_status=UNKNOWN, url_last_checked_at=None

    ctx = await open_db(db_path)
    async with ctx as db:
        run_id = await start_run(db, region="", keywords=())
        await insert_jobs(db, run_id, [day1])
        await insert_jobs(db, run_id, [day2])
        cur = await db.execute(
            "SELECT url_status, url_last_checked_at FROM jobs WHERE id=?",
            (day1.id,),
        )
        row = await cur.fetchone()

    assert row[0] == "live"
    assert row[1] == t1.isoformat()


@pytest.mark.asyncio
async def test_upsert_lets_definitive_outcomes_overwrite(tmp_path: Path) -> None:
    """If the new row carries url_status=live or gone, it MUST overwrite
    whatever was there before — definitive outcomes are authoritative."""
    db_path = tmp_path / "overwrite.db"
    t1 = datetime(2026, 5, 23, tzinfo=UTC)
    t2 = datetime(2026, 5, 24, tzinfo=UTC)

    day1 = _job(url_status=UrlStatus.LIVE, url_last_checked_at=t1)
    day2 = _job(url_status=UrlStatus.GONE, url_last_checked_at=t2)

    ctx = await open_db(db_path)
    async with ctx as db:
        run_id = await start_run(db, region="", keywords=())
        await insert_jobs(db, run_id, [day1])
        await insert_jobs(db, run_id, [day2])
        cur = await db.execute(
            "SELECT url_status, url_last_checked_at FROM jobs WHERE id=?",
            (day1.id,),
        )
        row = await cur.fetchone()

    assert row[0] == "gone"
    assert row[1] == t2.isoformat()
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `uv run pytest tests/storage/test_db_migration.py -v`

Expected:
- `test_insert_round_trips_url_status_and_check_time` → FAIL with parameter-count mismatch (`_INSERT_JOB` placeholders don't match the row tuple).
- `test_upsert_preserves_earned_freshness_on_listing_only_recrawl` → FAIL — current `INSERT OR REPLACE` overwrites the `live` signal with `unknown`.
- `test_upsert_lets_definitive_outcomes_overwrite` → likely PASS coincidentally if the round-trip test is skipped/failing earlier, but we'll verify after the fix.

- [ ] **Step 3: Update `_job_to_row` and `_INSERT_JOB` in `src/jma/storage/db.py`**

Replace `_job_to_row` with:

```python
def _job_to_row(j: Job) -> tuple:
    return (
        j.id, j.canonical_id, j.source, j.source_internal_id,
        j.title, j.title_raw, j.company,
        j.location.country, j.location.city, j.location.district, j.location.work_mode.value,
        j.salary.min, j.salary.max, j.salary.currency, j.salary.period.value,
        j.salary.months_per_year, j.salary.raw, 1 if j.salary.parsed else 0,
        j.experience.min_years, j.experience.max_years, j.experience.raw,
        json.dumps(j.skills_raw), json.dumps(j.skills_canonical),
        j.seniority.value, j.responsibilities_summary, j.description_text,
        j.posted_at.isoformat() if j.posted_at else None,
        j.fetched_at.isoformat(), j.url, j.raw_payload_ref, j.data_quality,
        j.url_status.value,
        j.url_last_checked_at.isoformat() if j.url_last_checked_at else None,
    )
```

Replace `_INSERT_JOB` with the upsert (33 columns, 33 placeholders, 32 `DO UPDATE SET` entries — every column except the PK `id`):

```python
# NOTE: see docs/adr/0003-url-freshness-as-durable-signal.md.
# All non-freshness columns use latest-wins (excluded.X). The two
# freshness columns are conditional: a transient re-insert (where
# url_status is 'unknown') must NOT overwrite a previously earned
# 'live'/'gone' signal. The broader "merge by confidence" question
# for company / salary / etc. is a tracked follow-up (see ADR).
_INSERT_JOB = """
INSERT INTO jobs (
  id, canonical_id, source, source_internal_id,
  title, title_raw, company,
  location_country, location_city, location_district, location_work_mode,
  salary_min, salary_max, salary_currency, salary_period,
  salary_months_per_year, salary_raw, salary_parsed,
  experience_min_years, experience_max_years, experience_raw,
  skills_raw_json, skills_canonical_json,
  seniority, responsibilities_summary, description_text,
  posted_at, fetched_at, url, raw_payload_ref, data_quality,
  url_status, url_last_checked_at
) VALUES (?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?, ?,?,?, ?,?,?,?,?, ?,?)
ON CONFLICT(id) DO UPDATE SET
  canonical_id             = excluded.canonical_id,
  source                   = excluded.source,
  source_internal_id       = excluded.source_internal_id,
  title                    = excluded.title,
  title_raw                = excluded.title_raw,
  company                  = excluded.company,
  location_country         = excluded.location_country,
  location_city            = excluded.location_city,
  location_district        = excluded.location_district,
  location_work_mode       = excluded.location_work_mode,
  salary_min               = excluded.salary_min,
  salary_max               = excluded.salary_max,
  salary_currency          = excluded.salary_currency,
  salary_period            = excluded.salary_period,
  salary_months_per_year   = excluded.salary_months_per_year,
  salary_raw               = excluded.salary_raw,
  salary_parsed            = excluded.salary_parsed,
  experience_min_years     = excluded.experience_min_years,
  experience_max_years     = excluded.experience_max_years,
  experience_raw           = excluded.experience_raw,
  skills_raw_json          = excluded.skills_raw_json,
  skills_canonical_json    = excluded.skills_canonical_json,
  seniority                = excluded.seniority,
  responsibilities_summary = excluded.responsibilities_summary,
  description_text         = excluded.description_text,
  posted_at                = excluded.posted_at,
  fetched_at               = excluded.fetched_at,
  url                      = excluded.url,
  raw_payload_ref          = excluded.raw_payload_ref,
  data_quality             = excluded.data_quality,
  url_status               = CASE
      WHEN excluded.url_status IN ('live','gone') THEN excluded.url_status
      ELSE jobs.url_status
  END,
  url_last_checked_at      = CASE
      WHEN excluded.url_status IN ('live','gone') THEN excluded.url_last_checked_at
      ELSE jobs.url_last_checked_at
  END
"""
```

- [ ] **Step 4: Run the round-trip + preservation tests**

Run: `uv run pytest tests/storage/test_db_migration.py -v`

Expected: all 5 tests pass.

- [ ] **Step 5: Run the full storage suite to confirm no regressions**

Run: `uv run pytest tests/storage -v`

Expected: all green. Existing inserts work because the two new fields have defaults on `Job`, and non-freshness columns keep the same overwrite semantic the previous `INSERT OR REPLACE` provided.

- [ ] **Step 6: Commit**

```bash
git add src/jma/storage/db.py tests/storage/test_db_migration.py
git commit -m "feat(storage): conditional upsert preserves earned url_status signal (#8)"
```

---

### Task 4: Pure helper `_apply_url_freshness(job, *, status_code, checked_at)`

**Files:**
- Create: `tests/sources/test_url_freshness.py`
- Modify: `src/jma/sources/testerhome.py`

The helper has **three branches** (see [ADR 0003](../../adr/0003-url-freshness-as-durable-signal.md)):

| `status_code` | `url_status` | `url_last_checked_at` | `data_quality` |
|---|---|---|---|
| 200 | `LIVE` | `checked_at` | unchanged |
| 404, 410 | `GONE` | `checked_at` | unchanged (decoupled — see ADR) |
| anything else (3xx, 429, other 4xx, 5xx, …) | **preserve** prior | **preserve** prior | unchanged |

- [ ] **Step 1: Write the failing helper tests**

Create `tests/sources/test_url_freshness.py`:

```python
from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus
from jma.sources.testerhome import _apply_url_freshness


def _job(**overrides) -> Job:
    base = dict(
        id=job_id(source="testerhome", internal_id="1", title="t",
                  company=None, city=None),
        canonical_id=canonical_id(title="t", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime.now(UTC),
        url="https://x/",
        raw_payload_ref="x.gz",
    )
    base.update(overrides)
    return Job(**base)


def test_200_marks_live_and_does_not_touch_data_quality() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    out = _apply_url_freshness(_job(), status_code=200, checked_at=now)
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == now
    assert out.data_quality == 1.0


def test_404_marks_gone_and_does_not_touch_data_quality() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    out = _apply_url_freshness(_job(), status_code=404, checked_at=now)
    assert out.url_status is UrlStatus.GONE
    assert out.url_last_checked_at == now
    assert out.data_quality == 1.0


def test_410_marks_gone() -> None:
    out = _apply_url_freshness(_job(), status_code=410,
                                checked_at=datetime.now(UTC))
    assert out.url_status is UrlStatus.GONE


def test_500_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=500,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_429_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=429,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_3xx_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.GONE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=302,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.GONE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_other_4xx_is_transient_preserves_prior_status() -> None:
    """403 (auth) and 401 are not 'gone' — the resource may exist behind auth."""
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=403,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE


def test_transient_on_fresh_job_keeps_unknown_defaults() -> None:
    """A 429 on a Job that has never been verified leaves url_status=UNKNOWN
    and url_last_checked_at=None. We don't fake a 'we tried' timestamp."""
    out = _apply_url_freshness(_job(), status_code=429,
                                checked_at=datetime.now(UTC))
    assert out.url_status is UrlStatus.UNKNOWN
    assert out.url_last_checked_at is None


def test_helper_is_idempotent_on_repeat_definitive_outcome() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    once = _apply_url_freshness(_job(), status_code=404, checked_at=now)
    twice = _apply_url_freshness(once, status_code=404, checked_at=now)
    assert once == twice
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/sources/test_url_freshness.py -v`

Expected: 9 failures — `_apply_url_freshness` not exported.

- [ ] **Step 3: Add `_apply_url_freshness` to `src/jma/sources/testerhome.py`**

Append below `_enrich_from_detail` (added by issue #7's plan):

```python
def _apply_url_freshness(
    job: Job,
    *,
    status_code: int,
    checked_at: datetime,
) -> Job:
    """Tag a Job with url_status based on a detail-fetch outcome.

    Durable-signal model (see docs/adr/0003-url-freshness-as-durable-signal.md):

    - 200            → url_status=LIVE,  url_last_checked_at=checked_at
    - 404, 410       → url_status=GONE,  url_last_checked_at=checked_at
    - anything else  → preserve prior url_status and url_last_checked_at
                       (3xx, 429, other 4xx, 5xx are all 'we don't know
                        anything new'; never erase an earned signal).

    data_quality is intentionally not touched by this helper.
    """
    if status_code == 200:
        return job.model_copy(update={
            "url_status": UrlStatus.LIVE,
            "url_last_checked_at": checked_at,
        })
    if status_code in (404, 410):
        return job.model_copy(update={
            "url_status": UrlStatus.GONE,
            "url_last_checked_at": checked_at,
        })
    return job
```

Add `UrlStatus` and `datetime` to the existing imports at the top of `testerhome.py` if not already present.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `uv run pytest tests/sources/test_url_freshness.py -v`

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jma/sources/testerhome.py tests/sources/test_url_freshness.py
git commit -m "feat(sources): _apply_url_freshness as durable signal helper (#8)"
```

---

### Task 5: Wire freshness into `_enrich_page`

**Files:**
- Modify: `src/jma/sources/testerhome.py`
- Modify: `tests/sources/test_testerhome_with_detail.py` (created by issue #7)

- [ ] **Step 1: Update `_enrich_page` to call `_apply_url_freshness` for every detail-fetch outcome**

Replace the `_enrich_page` method (added by issue #7 Task 5) with:

```python
async def _enrich_page(self, page_jobs: list[Job]) -> list[Job]:
    """Fetch each job's detail page, merge data, and tag freshness.

    On any per-job exception (network error, etc.), the listing-only Job
    is appended unchanged — freshness for that row stays at its prior DB
    value via the upsert's conditional clause (ADR 0003).
    """
    if not self._cfg.detail.enabled:
        return page_jobs
    enriched: list[Job] = []
    for job in page_jobs:
        try:
            status, _, body, _ = await self._fetch_one(job.url)
            checked_at = datetime.now(UTC)
            if status == 200:
                detail = _parse_detail(body, self._cfg)
                job_with_detail = _enrich_from_detail(
                    job, detail, source_name=self.name
                )
                enriched.append(
                    _apply_url_freshness(
                        job_with_detail,
                        status_code=status,
                        checked_at=checked_at,
                    )
                )
            else:
                enriched.append(
                    _apply_url_freshness(
                        job, status_code=status, checked_at=checked_at,
                    )
                )
        except Exception:  # noqa: BLE001
            enriched.append(job)
        await self._sleep(self._cfg.rate.delay_ms / 1000.0)
    return enriched
```

- [ ] **Step 2: Update the integration tests from issue #7**

In `tests/sources/test_testerhome_with_detail.py`, modify `test_crawl_with_detail_enabled_populates_company_and_salary` — add these assertions at the end:

```python
    assert job.url_status is UrlStatus.LIVE
    assert job.url_last_checked_at is not None
    assert job.data_quality == 1.0   # explicitly unchanged — no quality coupling
```

And modify `test_crawl_with_detail_falls_back_on_detail_404` — replace the final assertions with:

```python
    # Listing-only data preserved; freshness reflects the 404.
    assert len(result.jobs) == 1
    j = result.jobs[0]
    assert j.company is None
    assert j.url_status is UrlStatus.GONE
    assert j.url_last_checked_at is not None
    assert j.data_quality == 1.0   # ADR 0003: gone does NOT lower data_quality
```

Add a new integration test asserting the durable-signal behavior end-to-end:

```python
@pytest.mark.asyncio
async def test_transient_500_does_not_overwrite_prior_live_signal(
    tmp_path: Path, respx_mock,
) -> None:
    """If a row was 'live' yesterday and today's detail returns 500, the
    persisted row must still be 'live' — verified through the full
    crawl + storage round trip."""
    # ... mock listing + 500 detail; pre-populate DB with a Job at LIVE; run
    # crawl with --with-detail; assert DB row is still LIVE.
    # (Concrete fixture wiring follows the same shape as the existing
    # detail tests in this file.)
```

- [ ] **Step 3: Run the integration suite**

Run: `uv run pytest tests/sources -v`

Expected: all green; both detail-on and detail-404 paths exercise the freshness branches, and the new test locks the durable-signal end-to-end behavior.

- [ ] **Step 4: Commit**

```bash
git add src/jma/sources/testerhome.py tests/sources/test_testerhome_with_detail.py
git commit -m "feat(sources): _enrich_page tags url_status from detail fetch (#8)"
```

---

### Task 6: CLI summary — surface `gone_urls=N` only when we checked

**Files:**
- Modify: `src/jma/cli.py`
- Create: `tests/cli/test_summary.py`

The segment is **omitted** when no Job in the run has `url_last_checked_at` set — that's the signal that this Run didn't do detail fetches at all, so there's no freshness verdict to report. When detail did run, `gone_urls=0` is meaningful: "we checked, none gone."

- [ ] **Step 1: Write failing CLI summary tests**

Create `tests/cli/test_summary.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

from jma.cli import _summary_lines
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
    UrlStatus,
)


def _job(*, status: UrlStatus, checked: bool, suffix: str = "") -> Job:
    return Job(
        id=job_id(source="testerhome", internal_id=f"{status.value}{suffix}",
                  title="t", company=None, city=None),
        canonical_id=canonical_id(title=f"t{suffix}", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime.now(UTC),
        url=f"https://x/{status.value}{suffix}",
        raw_payload_ref="x.gz",
        url_status=status,
        url_last_checked_at=datetime.now(UTC) if checked else None,
    )


def test_summary_includes_gone_count_when_detail_ran() -> None:
    jobs = (
        _job(status=UrlStatus.LIVE, checked=True, suffix="a"),
        _job(status=UrlStatus.GONE, checked=True, suffix="b"),
        _job(status=UrlStatus.GONE, checked=True, suffix="c"),
    )
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls=2" in src_line


def test_summary_includes_gone_zero_when_detail_ran_and_all_live() -> None:
    jobs = (_job(status=UrlStatus.LIVE, checked=True, suffix="a"),)
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls=0" in src_line


def test_summary_omits_gone_segment_for_listing_only_crawl() -> None:
    """No Job has url_last_checked_at -> the source didn't do detail fetches.
    Don't print gone_urls=0 (misleading); omit the segment entirely."""
    jobs = (
        _job(status=UrlStatus.UNKNOWN, checked=False, suffix="a"),
        _job(status=UrlStatus.UNKNOWN, checked=False, suffix="b"),
    )
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls" not in src_line
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest tests/cli/test_summary.py -v`

Expected: FAIL — `gone_urls=` not in summary.

- [ ] **Step 3: Update `_summary_lines` in `src/jma/cli.py`**

Replace the body of the `if r.status is SourceStatus.OK:` branch (around current lines 59–63) with:

```python
if r.status is SourceStatus.OK:
    line = (
        f"  {r.source:<11}: ok    pages={r.pages_fetched}  jobs={n}"
    )
    if any(j.url_last_checked_at is not None for j in r.jobs):
        gone = sum(1 for j in r.jobs if j.url_status is UrlStatus.GONE)
        line += f"   gone_urls={gone}"
    line += f"   elapsed={r.elapsed_ms/1000:.1f}s"
    if r.reason.startswith("partial:"):
        line += f"  {r.reason}"
    lines.append(line)
```

Add `UrlStatus` to the imports at the top of `cli.py` if not already imported.

- [ ] **Step 4: Run the CLI tests to confirm they pass**

Run: `uv run pytest tests/cli/test_summary.py -v`

Expected: 3 passed.

- [ ] **Step 5: Run the full CLI suite**

Run: `uv run pytest tests/cli -v`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/jma/cli.py tests/cli/test_summary.py
git commit -m "feat(cli): summary reports gone_urls only when detail ran (#8)"
```

---

### Task 7: Document the freshness vocabulary in `CONTEXT.md`

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Add a `## URL freshness` glossary section**

Append to `CONTEXT.md` (after `## Source`, since that's currently the last section):

```markdown
## URL freshness

A [[JobObservation]]'s `url` is captured at listing time and persists in
the DB forever — but the underlying forum post can be deleted by the
author (e.g. when the role is filled). `url_status` records the
**durable best-known truth** about whether the URL still resolves, not
the most recent raw HTTP outcome:

- `live` — the last detail-fetch returned 200.
- `gone` — the last detail-fetch returned 404 or 410. Aggregations
  filter on `url_status='gone'` to discount or drop these rows. (5xx
  is *not* in this set: a server outage is not evidence that a post
  was deleted — see [ADR 0003](docs/adr/0003-url-freshness-as-durable-signal.md).)
- `unknown` — the URL has never been verified. Either the row was
  inserted from a listing-only crawl, or every detail-fetch attempt
  so far returned a transient outcome (3xx, 429, 5xx, network error).

`url_last_checked_at` is the UTC timestamp of the last detail-fetch
that produced a *definitive* outcome (200 / 404 / 410). Transient
outcomes never write either field — they preserve whatever signal we
last earned. A row whose `url_last_checked_at IS NULL` has never been
verified; aggregation queries should treat such rows differently from
those that were verified in the past and may have drifted.

Listing-only crawls (default `jma crawl`, no `--with-detail`) do not
update freshness for any row. To detect stale URLs, run with
`--with-detail`.
```

- [ ] **Step 2: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(context): glossary entry for URL freshness (#8)"
```

---

### Task 8: Final regression + lint

**Files:** none (verification only).

- [ ] **Step 1: Full suite**

Run: `uv run pytest`

Expected: all green.

- [ ] **Step 2: Lint + format**

Run: `uv run ruff check . && uv run ruff format --check .`

Expected: no errors. Amend the relevant commit if anything turns up.

- [ ] **Step 3: End-to-end smoke (optional)**

Run: `uv run jma crawl --region Hangzhou --keywords "测试" --max-pages 1 --max-jobs 3 --with-detail -v`

Expected: summary line contains `gone_urls=N`. Spot-check the DB:

```bash
sqlite3 data/jobs.db "SELECT url_status, url_last_checked_at, data_quality FROM jobs ORDER BY fetched_at DESC LIMIT 5;"
```

Expected: recently-crawled rows have non-NULL `url_last_checked_at` (those that got a definitive answer); `data_quality` is uniformly `1.0` regardless of `url_status` (decoupled per ADR 0003).

Then run the same command **without** `--with-detail`:

```bash
uv run jma crawl --region Hangzhou --keywords "测试" --max-pages 1 --max-jobs 3 -v
```

Expected: summary line **does not** contain `gone_urls=`. Existing rows whose `url_status` was previously `live` or `gone` still show those values in the DB — the listing-only re-insert did not overwrite them.

---

## Out of Scope (deliberate deferrals)

- **Standalone `jma reprobe` command** — re-running detail fetches on aging rows. Once `--with-detail` is in production, every fresh crawl already refreshes the URLs it sees on the listing page. A dedicated reprobe is only useful for URLs that have fallen off the listing entirely; measure first, build later. Note this as a follow-up in the PR description.
- **Lowering `data_quality` for stale URLs** (issue #8's Option 2). Explicitly rejected — see [ADR 0003](../../adr/0003-url-freshness-as-durable-signal.md). Aggregations filter on `url_status='gone'` directly.
- **Expanding `UrlStatus`** to capture redirect chains (3xx), soft-deletes, DNS failures, or auth-required states. Current scope is HTTP status codes mapped to three states. Anything richer is a separate ADR.
- **Broader "merge by confidence" upsert policy** for other detail-fetched fields (`company`, `salary`, `description_text`, `posted_at`, etc.). They have the same overwrite-on-listing-only-recrawl problem this PR fixes for freshness, but the fix needs its own design conversation. Track as a follow-up issue; mention in the PR description and in the comment above `_INSERT_JOB`.
- **Second timestamp `url_last_attempt_at`** to distinguish "never tried" from "tried but never got a definitive answer". Deferred; cheap to add later as another idempotent ALTER if any aggregation ever needs the distinction.

---

## Self-Review Notes

- **Spec coverage** (against issue #8's "Options for human to decide"):
  - Option 1 (`url_valid` / `url_checked_at` column) → covered by Tasks 1–3.
  - Option 2 (lower `data_quality` for stale URLs) → **explicitly rejected**, see ADR 0003. The PR description should call this out so reviewers don't read it as an oversight.
  - Option 3 (docs only) → covered as a *complement* in Task 7, not as the primary fix.
  - Option 4 (detail-page crawl validates URL) → handled via dependency on issue #7's `_enrich_page`.
- **Acceptance criteria** (from issue):
  - "Stale URLs detectable in the DB" → `url_status='gone'` is queryable; covered by Tasks 2–3.
  - "`jma crawl` output summarises how many stored URLs were found stale" → Task 6, scoped to the current Run (per-Run count, not whole-DB). The DB-wide query is one-line SQL if the operator wants it; a `jma stats` subcommand is the right home, not the crawl summary.
  - "Re-probe respects existing rate-limit config" → Task 5's loop reuses `self._cfg.rate.delay_ms`.
- **Durable signal model:** the helper is pure and stateless. The "preserve prior on transient" rule lives in two places that have to stay in sync: the helper (returns the job unchanged) AND the SQL upsert (`CASE WHEN excluded.url_status IN ('live','gone') …`). Tests in Task 3 lock the SQL behaviour; tests in Task 4 lock the helper behaviour. If you change one, change the other.
- **Migration safety:** Task 2's migration is idempotent — running it twice (or on a fresh DB) is a no-op. The `_DDL` includes the columns up-front for new DBs, and the ALTER catches the `duplicate column name` error on already-migrated DBs.
- **Schema fields touched:** only the two new columns. `data_quality` is left alone.
- **Type consistency:** `url_status` is `UrlStatus(StrEnum)` everywhere — Job model, helper signature, CLI summary, tests. Matches the convention set by `WorkMode`, `Seniority`, `SalaryPeriod`, `SourceStatus`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-issue-8-url-freshness.md`. Companion ADR at `docs/adr/0003-url-freshness-as-durable-signal.md`.
