"""24h URL cache (spec §5 cache TTL)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
    ts = (now or datetime.now(UTC)).isoformat()
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
    moment = now or datetime.now(UTC)
    if row[3] != 200:
        return None
    if moment - fetched_at >= _TTL:
        return None
    return CacheHit(url=row[0], blob_ref=row[1], fetched_at=fetched_at, status_code=row[3])
