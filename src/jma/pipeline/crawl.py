"""Crawl orchestration (spec §11 slice 1.11)."""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from pathlib import Path

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
    async with conn as db:
        run_id = await start_run(db, region=region, keywords=keywords)

        async def on_fetch(url: str, status_code: int, blob_ref: str) -> None:
            await urlcache.put(
                db,
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

        await insert_jobs(db, run_id, list(result.jobs))
        await finish_run(db, run_id=run_id, source_results=[result])
        return run_id, [result]


async def _noop(url: str, status_code: int, blob_ref: str) -> None:
    return None
