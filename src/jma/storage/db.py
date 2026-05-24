"""SQLite bootstrap + Run / Job persistence (spec §5)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from jma.domain.models import Job, Run, SourceResult

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
    data_quality             REAL NOT NULL DEFAULT 1.0,
    url_status               TEXT NOT NULL DEFAULT 'unknown',
    url_last_checked_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_canonical   ON jobs(canonical_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source      ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched_at  ON jobs(fetched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_city        ON jobs(location_city);

CREATE TABLE IF NOT EXISTS run_jobs (
    run_id          TEXT NOT NULL REFERENCES runs(id),
    job_id          TEXT NOT NULL REFERENCES jobs(id),
    raw_payload_ref TEXT NOT NULL,
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


class _DbContext:
    """Async context manager wrapping an already-opened aiosqlite connection."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def __aenter__(self) -> aiosqlite.Connection:
        return self._conn

    async def __aexit__(self, *_: object) -> None:
        await self._conn.close()


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


async def open_db(path: str | Path) -> _DbContext:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(p))
    await conn.executescript(_DDL)
    await _apply_jobs_migrations(conn)
    return _DbContext(conn)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
        {
            "source": r.source,
            "status": r.status.value,
            "reason": r.reason,
            "pages_fetched": r.pages_fetched,
            "elapsed_ms": r.elapsed_ms,
        }
        for r in source_results
    ]
    await conn.execute(
        "UPDATE runs SET finished_at=?, source_results_json=? WHERE id=?",
        (_utc_now_iso(), json.dumps(payload), run_id),
    )
    await conn.commit()


def _job_to_row(j: Job) -> tuple:
    return (
        j.id,
        j.canonical_id,
        j.source,
        j.source_internal_id,
        j.title,
        j.title_raw,
        j.company,
        j.location.country,
        j.location.city,
        j.location.district,
        j.location.work_mode.value,
        j.salary.min,
        j.salary.max,
        j.salary.currency,
        j.salary.period.value,
        j.salary.months_per_year,
        j.salary.raw,
        1 if j.salary.parsed else 0,
        j.experience.min_years,
        j.experience.max_years,
        j.experience.raw,
        json.dumps(j.skills_raw),
        json.dumps(j.skills_canonical),
        j.seniority.value,
        j.responsibilities_summary,
        j.description_text,
        j.posted_at.isoformat() if j.posted_at else None,
        j.fetched_at.isoformat(),
        j.url,
        j.raw_payload_ref,
        j.data_quality,
        j.url_status.value,
        j.url_last_checked_at.isoformat() if j.url_last_checked_at else None,
    )


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


async def insert_jobs(
    conn: aiosqlite.Connection,
    run_id: str,
    jobs: Iterable[Job],
) -> None:
    jobs = list(jobs)
    rows = [_job_to_row(j) for j in jobs]
    if not rows:
        return
    await conn.executemany(_INSERT_JOB, rows)
    await conn.executemany(
        "INSERT OR IGNORE INTO run_jobs (run_id, job_id, raw_payload_ref) VALUES (?, ?, ?)",
        [(run_id, j.id, j.raw_payload_ref) for j in jobs],
    )
    await conn.commit()


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


async def latest_finished_run(conn: aiosqlite.Connection) -> Run | None:
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


async def get_run(conn: aiosqlite.Connection, run_id: str) -> Run | None:
    """Fetch a Run by id; finished_at may be None."""
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
