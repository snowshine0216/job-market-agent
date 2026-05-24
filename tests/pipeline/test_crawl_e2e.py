import json
from pathlib import Path

import aiosqlite
import httpx
import pytest
import respx

from jma.domain.models import (
    SourceResult,
    SourceStatus,
)
from jma.pipeline.crawl import run
from jma.sources.base import JobSource, load_source_config
from jma.sources.bing import BingAggregatorSource
from jma.sources.http import AsyncHttpClient

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/bing.yaml"

# Minimal SerpAPI JSON with one on-target result.
FIX_ONE_JOB = json.dumps({
    "organic_results": [
        {
            "title": "AI Agent Engineer | BOSS直聘",
            "link": "https://www.zhipin.com/job_detail/42.html",
            "snippet": "Hangzhou 20-40K 3-5年",
        }
    ]
})
FIX_EMPTY = json.dumps({"organic_results": []})


def _factory(tmp_path: Path):
    async def _no_sleep(_s: float) -> None:
        return None

    cfg = load_source_config(CFG_PATH)

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get):
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        return BingAggregatorSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            api_key="testkey",
            sleep=_no_sleep,
            on_fetch=on_fetch,
            cache_get=cache_get,
        )

    return _make


@respx.mock
@pytest.mark.asyncio
async def test_end_to_end_writes_runs_jobs_run_jobs_cache_blob(tmp_path: Path) -> None:
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=FIX_ONE_JOB)
    )

    run_id, source_results = await run(
        region="Hangzhou",
        keywords=("AI agent",),
        source_factory=_factory(tmp_path),
        db_path=tmp_path / "data/jobs.db",
        data_root=tmp_path,
        max_pages=1,
        max_jobs=100,
        use_cache=True,
    )

    assert isinstance(run_id, str) and len(run_id) == 32
    assert len(source_results) == 1
    assert source_results[0].status.value == "ok"
    assert len(source_results[0].jobs) >= 1

    # DB invariants.
    async with aiosqlite.connect(str(tmp_path / "data/jobs.db")) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM runs WHERE id=?", (run_id,))
        assert (await cur.fetchone())[0] == 1
        cur = await conn.execute("SELECT COUNT(*) FROM jobs")
        n_jobs = (await cur.fetchone())[0]
        assert n_jobs >= 1
        cur = await conn.execute("SELECT canonical_id FROM jobs LIMIT 1")
        (canon,) = await cur.fetchone()
        assert canon != ""
        cur = await conn.execute("SELECT COUNT(*) FROM run_jobs WHERE run_id=?", (run_id,))
        assert (await cur.fetchone())[0] == n_jobs
        # run_jobs.raw_payload_ref is not null (spec §2 row 17)
        cur = await conn.execute(
            "SELECT COUNT(*) FROM run_jobs WHERE run_id=? AND raw_payload_ref IS NOT NULL",
            (run_id,),
        )
        assert (await cur.fetchone())[0] == n_jobs
        cur = await conn.execute("SELECT COUNT(*) FROM url_cache WHERE status_code=200")
        assert (await cur.fetchone())[0] >= 1

    # Blob present with .json.gz suffix.
    blobs_dir = tmp_path / "raw/bing"
    assert blobs_dir.exists()
    assert any(p.suffix == ".gz" for p in blobs_dir.rglob("*"))


# ---------------------------------------------------------------------------
# L1: second run should hit cache and not re-fetch
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_second_run_hits_cache_for_fresh_urls(tmp_path: Path) -> None:
    """L1: URLs fetched < 24h ago must be read from cache; respx call count stays at 0 on run 2."""
    route = respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=FIX_ONE_JOB)
    )
    db_path = tmp_path / "data/jobs.db"

    # Run 1 — populates cache.
    run1_id, run1_results = await run(
        region="",
        keywords=("",),
        source_factory=_factory(tmp_path),
        db_path=db_path,
        data_root=tmp_path,
        max_pages=1,
        max_jobs=100,
        use_cache=True,
    )
    assert run1_results[0].status == SourceStatus.OK
    call_count_after_run1 = route.call_count
    assert call_count_after_run1 >= 1  # sanity: did actually fetch on run 1

    # Run 2 — should hit cache; respx call count must not increase.
    run2_id, run2_results = await run(
        region="",
        keywords=("",),
        source_factory=_factory(tmp_path),
        db_path=db_path,
        data_root=tmp_path,
        max_pages=1,
        max_jobs=100,
        use_cache=True,
    )
    assert run2_results[0].status == SourceStatus.OK
    assert route.call_count == call_count_after_run1, (
        "SerpAPI was re-fetched despite fresh cache entry"
    )


# ---------------------------------------------------------------------------
# L1 + --no-cache: both runs hit network; cache rows are still written
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_no_cache_skips_reads_but_writes(tmp_path: Path) -> None:
    """L1: --no-cache skips cache reads so network is hit both runs; writes still happen."""
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=FIX_ONE_JOB)
    )
    db_path = tmp_path / "data/jobs.db"

    for _ in range(2):
        await run(
            region="",
            keywords=("",),
            source_factory=_factory(tmp_path),
            db_path=db_path,
            data_root=tmp_path,
            max_pages=1,
            max_jobs=100,
            use_cache=False,
        )

    # Cache rows must still be written even with use_cache=False.
    async with aiosqlite.connect(str(db_path)) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM url_cache WHERE status_code=200")
        count = (await cur.fetchone())[0]
    assert count >= 1, "url_cache rows should be written even when use_cache=False"


# ---------------------------------------------------------------------------
# L2: unhandled exception in source.crawl must still finish the Run row
# ---------------------------------------------------------------------------


class _ExplodingSource:
    """Fake JobSource that raises mid-crawl."""

    name = "exploding-source"

    async def crawl(
        self, region: str, keywords: tuple, max_pages: int, max_jobs: int
    ) -> SourceResult:
        raise RuntimeError("boom — simulated crawl failure")


@pytest.mark.asyncio
async def test_unhandled_source_exception_still_finishes_run(tmp_path: Path) -> None:
    """L2: if source.crawl raises, finish_run must be called; runs row must not have NULL finished_at."""

    def _exploding_factory(ac, on_fetch, cache_get) -> JobSource:
        return _ExplodingSource()

    db_path = tmp_path / "data/jobs.db"
    with pytest.raises(RuntimeError, match="boom"):
        await run(
            region="",
            keywords=("",),
            source_factory=_exploding_factory,
            db_path=db_path,
            data_root=tmp_path,
            max_pages=1,
            max_jobs=100,
            use_cache=False,
        )

    async with aiosqlite.connect(str(db_path)) as conn:
        cur = await conn.execute("SELECT finished_at, source_results_json FROM runs")
        rows = await cur.fetchall()
    assert len(rows) == 1, "Expected exactly one run row"
    finished_at, source_results_json = rows[0]
    assert finished_at is not None, "finished_at must be set even after an exception"
    assert source_results_json is not None, (
        "source_results_json must be set even after an exception"
    )
    import json

    results = json.loads(source_results_json)
    assert len(results) == 1
    assert results[0]["status"] == "error"


# ---------------------------------------------------------------------------
# L3: cache rows must be tagged with the real source name, not a hardcoded literal
# ---------------------------------------------------------------------------


class _FakeNamedSource:
    """Fake JobSource whose name is configurable for testing L3."""

    def __init__(self, name: str, on_fetch, cache_get, data_root: Path) -> None:
        self.name = name
        self._on_fetch = on_fetch
        self._data_root = data_root

    async def crawl(
        self, region: str, keywords: tuple, max_pages: int, max_jobs: int
    ) -> SourceResult:
        url = "https://fake-source.example/jobs?page=1"
        from jma.storage import blobs as _blobs

        blob_ref = _blobs.write(root=self._data_root, source=self.name, url=url, body="<html/>")
        await self._on_fetch(url, 200, blob_ref)
        return SourceResult(source=self.name, status=SourceStatus.OK, jobs=())


@pytest.mark.asyncio
async def test_cache_rows_tagged_with_source_name(tmp_path: Path) -> None:
    """L3: url_cache.source must equal the source's name attribute, not a hardcoded string."""
    fake_name = "fake-source"

    def _named_factory(ac, on_fetch, cache_get) -> JobSource:
        return _FakeNamedSource(
            name=fake_name, on_fetch=on_fetch, cache_get=cache_get, data_root=tmp_path
        )

    db_path = tmp_path / "data/jobs.db"
    await run(
        region="",
        keywords=("",),
        source_factory=_named_factory,
        db_path=db_path,
        data_root=tmp_path,
        max_pages=1,
        max_jobs=100,
        use_cache=True,
    )

    async with aiosqlite.connect(str(db_path)) as conn:
        cur = await conn.execute("SELECT DISTINCT source FROM url_cache")
        sources = [row[0] for row in await cur.fetchall()]
    assert sources == [fake_name], f"Expected source={fake_name!r} but got {sources}"
