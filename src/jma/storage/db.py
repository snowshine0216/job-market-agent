"""SQLite bootstrap + Run / Job persistence (spec §5)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

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
    data_quality             REAL NOT NULL DEFAULT 1.0,
    url_status               TEXT NOT NULL DEFAULT 'unknown',
    url_last_checked_at      TEXT
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
        [(run_id, row[0]) for row in rows],
    )
    await conn.commit()
