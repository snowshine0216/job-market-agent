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
