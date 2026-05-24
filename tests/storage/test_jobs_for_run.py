"""Per-Run snapshot of raw_payload_ref via run_jobs.raw_payload_ref (spec §2 row 17)."""

from __future__ import annotations

from datetime import UTC, datetime

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
