"""Crawl orchestration (spec §11 slice 1.11)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from jma.domain.models import SourceResult, SourceStatus
from jma.sources.base import JobSource
from jma.storage import cache as urlcache
from jma.storage.cache import CacheHit
from jma.storage.db import finish_run, insert_jobs, open_db, start_run

# on_fetch: (url, status_code, blob_ref | None) -> None
_OnFetchFn = Callable[[str, int, "str | None"], Awaitable[None]]
# cache_get: (url) -> CacheHit | None
_CacheGetFn = Callable[[str], Awaitable["CacheHit | None"]]

SourceFactory = Callable[[httpx.AsyncClient, _OnFetchFn, _CacheGetFn], JobSource]


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

        try:
            async with httpx.AsyncClient() as ac:
                # Build the source once with no-op callbacks to discover source.name,
                # then rebuild with real callbacks that capture source.name (L3).
                _probe = source_factory(ac, _noop_on_fetch, _noop_cache_get)

                async def _on_fetch(url: str, status_code: int, blob_ref: str | None) -> None:
                    await urlcache.put(
                        db,
                        url=url,
                        source=_probe.name,  # L3: tag with the real source name
                        status_code=status_code,
                        blob_ref=blob_ref,
                    )

                async def _cache_get(url: str) -> CacheHit | None:
                    # L1: skip read when use_cache=False (--no-cache); always write via on_fetch
                    if not use_cache:
                        return None
                    return await urlcache.get(db, url=url)

                source = source_factory(ac, _on_fetch, _cache_get)

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

        except Exception as e:  # noqa: BLE001
            # L2: always finish_run so the runs row is never left dangling with NULL finished_at.
            error_result = SourceResult(
                source=_probe.name,
                status=SourceStatus.ERROR,
                reason=f"unhandled exception: {type(e).__name__}: {e}",
            )
            await finish_run(db, run_id=run_id, source_results=[error_result])
            raise

        return run_id, [result]


async def _noop_on_fetch(url: str, status_code: int, blob_ref: str | None) -> None:
    return None


async def _noop_cache_get(url: str) -> CacheHit | None:
    return None
