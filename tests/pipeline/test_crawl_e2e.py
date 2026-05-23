from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import httpx
import pytest
import respx

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
    UrlStatus,
)
from jma.pipeline.crawl import run
from jma.sources.base import JobSource, load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(
    encoding="utf-8"
)


def _factory(tmp_path: Path):
    async def _no_sleep(_s: float) -> None:
        return None

    cfg = load_source_config(CFG_PATH)

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get):
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        return TesterHomeSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            sleep=_no_sleep,
            on_fetch=on_fetch,
            cache_get=cache_get,
        )

    return _make


@respx.mock
@pytest.mark.asyncio
async def test_end_to_end_writes_runs_jobs_run_jobs_cache_blob(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )

    run_id, source_results = await run(
        region="Hangzhou",
        keywords=("AI agent",),
        source_factory=_factory(tmp_path),
        db_path=tmp_path / "data/jobs.db",
        data_root=tmp_path,
        max_pages=3,
        max_jobs=100,
        use_cache=True,
    )

    assert isinstance(run_id, str) and len(run_id) == 32
    assert len(source_results) == 1
    assert source_results[0].status.value == "ok"
    assert len(source_results[0].jobs) >= 1

    # DB invariants.
    import aiosqlite

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
        cur = await conn.execute("SELECT COUNT(*) FROM url_cache WHERE status_code=200")
        assert (await cur.fetchone())[0] >= 1

    # Blob present.
    blobs_dir = tmp_path / "raw/testerhome"
    assert blobs_dir.exists()
    assert any(p.suffix == ".gz" for p in blobs_dir.rglob("*"))


# ---------------------------------------------------------------------------
# L1: second run should hit cache and not re-fetch
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_second_run_hits_cache_for_fresh_urls(tmp_path: Path) -> None:
    """L1: URLs fetched < 24h ago must be read from cache; respx call count stays at 0 on run 2."""
    route1 = respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    route2 = respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    db_path = tmp_path / "data/jobs.db"

    # Run 1 — populates cache.
    run1_id, run1_results = await run(
        region="",
        keywords=("",),
        source_factory=_factory(tmp_path),
        db_path=db_path,
        data_root=tmp_path,
        max_pages=2,
        max_jobs=100,
        use_cache=True,
    )
    assert run1_results[0].status == SourceStatus.OK
    first_call_count_1 = route1.call_count
    first_call_count_2 = route2.call_count
    assert first_call_count_1 >= 1  # sanity: did actually fetch on run 1

    # Run 2 — should hit cache; respx call counts must not increase.
    run2_id, run2_results = await run(
        region="",
        keywords=("",),
        source_factory=_factory(tmp_path),
        db_path=db_path,
        data_root=tmp_path,
        max_pages=2,
        max_jobs=100,
        use_cache=True,
    )
    assert run2_results[0].status == SourceStatus.OK
    assert route1.call_count == first_call_count_1, (
        "page 1 was re-fetched despite fresh cache entry"
    )
    assert route2.call_count == first_call_count_2, (
        "page 2 was re-fetched despite fresh cache entry"
    )
    # Both runs produced same jobs.
    assert len(run1_results[0].jobs) == len(run2_results[0].jobs)


# ---------------------------------------------------------------------------
# L1 + --no-cache: both runs hit network; cache rows are still written
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_no_cache_skips_reads_but_writes(tmp_path: Path) -> None:
    """L1: --no-cache skips cache reads so network is hit both runs; writes still happen."""
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    db_path = tmp_path / "data/jobs.db"

    for _ in range(2):
        respx.get("https://testerhome.com/jobs?page=1").mock(
            return_value=httpx.Response(200, text=FIX_OK)
        )
        respx.get("https://testerhome.com/jobs?page=2").mock(
            return_value=httpx.Response(200, text=FIX_EMPTY)
        )
        await run(
            region="",
            keywords=("",),
            source_factory=_factory(tmp_path),
            db_path=db_path,
            data_root=tmp_path,
            max_pages=2,
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
# L3: cache rows must be tagged with the real source name, not "testerhome" literal
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


# ---------------------------------------------------------------------------
# L4: transient 500 on detail must NOT overwrite a previously earned LIVE signal
# ---------------------------------------------------------------------------


def _factory_detail_on(tmp_path: Path):
    """Like _factory but with detail enrichment enabled."""

    async def _no_sleep(_s: float) -> None:
        return None

    base_cfg = load_source_config(CFG_PATH)
    cfg = base_cfg.model_copy(
        update={"detail": base_cfg.detail.model_copy(update={"enabled": True})}
    )

    def _make(ac: httpx.AsyncClient, on_fetch, cache_get):
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        return TesterHomeSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            sleep=_no_sleep,
            on_fetch=on_fetch,
            cache_get=cache_get,
        )

    return _make


@respx.mock
@pytest.mark.asyncio
async def test_transient_500_does_not_overwrite_prior_live_signal(tmp_path: Path) -> None:
    """If a row was 'live' yesterday and today's detail returns 500, the
    persisted row must still be 'live' — verified through the full
    crawl + storage round trip.

    Note: placed in tests/pipeline/test_crawl_e2e.py (Option B) because the
    plan's own phrasing says "verified through the full crawl + storage round
    trip" — that is pipeline-level behaviour, not a source-unit concern. The
    existing source tests in test_testerhome_with_detail.py do not touch storage,
    so adding DB assertions there would require significant new setup. Here we
    reuse the established open_db + insert_jobs + pipeline.crawl.run pattern.
    """
    from jma.storage.db import insert_jobs, open_db, start_run

    db_path = tmp_path / "data/jobs.db"

    # The listing_ok.html fixture has topic 100 at Hangzhou.
    # Compute the job id that the crawler will produce for testerhome:/topics/100.
    pre_job_id = job_id(source="testerhome", internal_id="100", title="", company=None, city=None)
    yesterday = datetime.now(UTC) - timedelta(days=1)

    # Pre-populate the DB with a LIVE row for that job so we can verify it's preserved.
    pre_job = Job(
        id=pre_job_id,
        canonical_id=canonical_id(title="AI Agent Engineer", company=None, city="Hangzhou"),
        source="testerhome",
        source_internal_id="100",
        title="AI Agent Engineer",
        title_raw="【杭州·余杭】AI Agent Engineer 15-30K·14薪",
        company=None,
        location=Location(city="Hangzhou"),
        salary=Salary(),
        experience=Experience(),
        fetched_at=yesterday,
        url="https://testerhome.com/topics/100",
        raw_payload_ref="raw/testerhome/placeholder.html.gz",
        url_status=UrlStatus.LIVE,
        url_last_checked_at=yesterday,
    )

    ctx = await open_db(db_path)
    async with ctx as db:
        run_id_pre = await start_run(db, region="Hangzhou", keywords=("AI agent",))
        await insert_jobs(db, run_id_pre, [pre_job])

    # Mock listing returns FIX_OK (topic 100 matches Hangzhou + "AI agent").
    # Mock listing page 2 as empty so crawl stops.
    # Mock topic 100 detail as 500 (transient server error).
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    # Catch-all for all topic detail URLs: topic 100 returns 500 (the case under
    # test), topic 101 is filtered out by region (Beijing), topic 102 survives
    # both the Hangzhou-region and "AI agent" keyword filters and would also be
    # fetched. Using a regex catch-all keeps the test robust to fixture changes.
    respx.get(url__regex=r"https://testerhome\.com/topics/\d+").mock(
        return_value=httpx.Response(500, text="internal server error")
    )

    await run(
        region="Hangzhou",
        keywords=("AI agent",),
        source_factory=_factory_detail_on(tmp_path),
        db_path=db_path,
        data_root=tmp_path,
        max_pages=2,
        max_jobs=100,
        use_cache=False,
    )

    # After the crawl, the DB row for topic 100 must still reflect LIVE status.
    async with aiosqlite.connect(str(db_path)) as conn:
        cur = await conn.execute(
            "SELECT url_status, url_last_checked_at FROM jobs WHERE id=?",
            (pre_job_id,),
        )
        row = await cur.fetchone()

    assert row is not None, f"Job {pre_job_id} not found in DB after crawl"
    url_status, url_last_checked_at = row
    assert url_status == "live", (
        f"Expected url_status='live' but got {url_status!r}. "
        "A transient 500 must not erase an earned LIVE signal."
    )
    assert url_last_checked_at == yesterday.isoformat(), (
        f"url_last_checked_at must not change on transient 500; got {url_last_checked_at!r}"
    )
