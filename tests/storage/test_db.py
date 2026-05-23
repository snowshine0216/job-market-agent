from datetime import UTC, datetime
from pathlib import Path

import pytest

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
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
        fetched_at=datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
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
