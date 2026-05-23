from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jma.storage.cache import get, put
from jma.storage.db import open_db


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


@pytest.mark.asyncio
async def test_23h59m_row_is_fresh(tmp_path: Path) -> None:
    """A 200 row that is 23h 59m old is within the 24h TTL and must be returned."""
    t0 = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    async with await open_db(tmp_path / "jobs.db") as conn:
        await put(conn, url="https://x/y", source="testerhome",
                  status_code=200, blob_ref="ref/a.gz", now=t0)
        got = await get(conn, url="https://x/y", now=t0 + timedelta(hours=23, minutes=59))
    assert got is not None
    assert got.blob_ref == "ref/a.gz"


@pytest.mark.asyncio
async def test_24h01m_row_is_stale(tmp_path: Path) -> None:
    """A 200 row that is 24h 1m old is past the TTL and must be returned as None."""
    t0 = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    async with await open_db(tmp_path / "jobs.db") as conn:
        await put(conn, url="https://x/y", source="testerhome",
                  status_code=200, blob_ref="ref/b.gz", now=t0)
        got = await get(conn, url="https://x/y", now=t0 + timedelta(hours=24, minutes=1))
    assert got is None
