from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import pytest

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus
from jma.storage.db import insert_jobs, open_db, start_run

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


def _job(**overrides) -> Job:
    base = dict(
        id=job_id(source="testerhome", internal_id="9", title="t", company=None, city=None),
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
