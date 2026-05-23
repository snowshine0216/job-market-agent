from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(
    encoding="utf-8"
)


def _make_source(tmp_path: Path, ac: httpx.AsyncClient) -> TesterHomeSource:
    cfg = load_source_config(CFG_PATH)

    async def _no_sleep(_seconds: float) -> None:  # speed up backoff in tests
        return None

    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
    return TesterHomeSource(
        cfg=cfg,
        http=http,
        data_root=tmp_path,
        sleep=_no_sleep,  # also no inter-page delay
    )


@respx.mock
@pytest.mark.asyncio
async def test_listing_ok_extracts_three_items_no_region_no_kw_filter(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        # region="" disables region filter (kept items must equal empty region == always true via substring)
        result = await src.crawl(region="", keywords=("",), max_pages=1, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert len(result.jobs) == 3
    titles = [j.title_raw for j in result.jobs]
    assert any("AI Agent Engineer" in t for t in titles)
    # Salary parsed for items 1 and 3.
    assert any(j.salary.parsed for j in result.jobs)
    # Page-1 blob ref shared across items on the page.
    refs = {j.raw_payload_ref for j in result.jobs}
    assert len(refs) == 1


@respx.mock
@pytest.mark.asyncio
async def test_region_filter_drops_non_matching_city(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=100)
    cities = [j.location.city for j in result.jobs]
    assert "Beijing" not in cities
    assert "Hangzhou" in cities


@respx.mock
@pytest.mark.asyncio
async def test_keyword_filter_phrase_semantics(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        # "AI agent" matches the literal substring in items 1 and 3.
        result = await src.crawl(region="", keywords=("AI agent",), max_pages=1, max_jobs=100)
    titles = [j.title_raw.lower() for j in result.jobs]
    assert all("ai agent" in t for t in titles)
    assert len(result.jobs) == 2


@respx.mock
@pytest.mark.asyncio
async def test_empty_listing_on_page_1_returns_empty(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.EMPTY
    assert result.jobs == ()


@respx.mock
@pytest.mark.asyncio
async def test_empty_listing_on_page_N_returns_ok_with_collected(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert "end of listing" in result.reason
    assert len(result.jobs) == 3


@respx.mock
@pytest.mark.asyncio
async def test_partial_harvest_on_429_after_page_1(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"}, text="")
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=3, max_jobs=100)
    assert result.status == SourceStatus.OK
    assert result.reason.startswith("partial:")
    assert "page 2" in result.reason
    assert len(result.jobs) == 3


@respx.mock
@pytest.mark.asyncio
async def test_hard_block_on_page_1_returns_block_status(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(403, text="forbid")
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=2, max_jobs=100)
    assert result.status == SourceStatus.BLOCKED
    assert result.jobs == ()


@respx.mock
@pytest.mark.asyncio
async def test_max_jobs_truncates_exactly(tmp_path):
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=2, max_jobs=2)
    assert len(result.jobs) == 2
    assert result.reason == "max_jobs reached"


@respx.mock
@pytest.mark.asyncio
async def test_blob_not_written_on_blocked_response(tmp_path):
    """L4: blob must NOT be written when status code != 200 (e.g. 429)."""
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"}, text="")
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="", keywords=("",), max_pages=2, max_jobs=100)
    assert result.status == SourceStatus.RATE_LIMITED
    blobs_dir = tmp_path / "raw" / "testerhome"
    blob_files = list(blobs_dir.rglob("*.gz")) if blobs_dir.exists() else []
    assert blob_files == [], f"Expected no blobs but found {blob_files}"
