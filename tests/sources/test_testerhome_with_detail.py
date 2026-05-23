from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus, UrlStatus
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
_CFG_PATH = REPO / "config/sources/testerhome.yaml"
_FIX_DETAIL = REPO / "tests/fixtures/sources/testerhome/detail_basic.html"
_FIX_BLOCKED = REPO / "tests/fixtures/sources/testerhome/detail_blocked.html"

_LISTING_HTML = """
<html><body>
<div class="topics">
  <div class="topic">
    <div class="title"><a href="/topics/42">【上海】测试开发</a></div>
    <span class="time" title="2026-05-22T10:00:00+08:00">2d</span>
  </div>
</div>
</body></html>
"""


def _cfg_detail_on():
    base = load_source_config(_CFG_PATH)
    return base.model_copy(update={"detail": base.detail.model_copy(update={"enabled": True})})


def _cfg_detail_on_with_block_marker():
    base = _cfg_detail_on()
    return base.model_copy(
        update={
            "content_block_markers": ("系统繁忙，请稍后再试",),
        }
    )


async def _noop_sleep(_s: float) -> None:
    return None


def _make_source(cfg, tmp_path: Path, ac: httpx.AsyncClient) -> TesterHomeSource:
    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_noop_sleep)
    return TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path, sleep=_noop_sleep)


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_enabled_populates_company_and_salary(tmp_path: Path) -> None:
    cfg = _cfg_detail_on()
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text=_FIX_DETAIL.read_text(encoding="utf-8"))
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai",
            keywords=("测试",),
            max_pages=1,
            max_jobs=10,
        )

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.company == "上海冰鲸科技有限公司"
    assert job.salary.raw == "30k-50k·14薪"
    assert job.salary.parsed is True
    assert job.salary.min == 30000
    assert job.salary.max == 50000
    assert job.url_status is UrlStatus.LIVE
    assert job.url_last_checked_at is not None
    assert job.data_quality == 1.0   # explicitly unchanged — no quality coupling


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_disabled_skips_detail_fetch(tmp_path: Path) -> None:
    cfg = load_source_config(_CFG_PATH)  # detail.enabled = False from YAML
    assert cfg.detail.enabled is False

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    detail_route = respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text="should not be called")
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai",
            keywords=("测试",),
            max_pages=1,
            max_jobs=10,
        )

    assert detail_route.call_count == 0
    assert len(result.jobs) == 1
    assert result.jobs[0].company is None


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_falls_back_on_detail_404(tmp_path: Path) -> None:
    cfg = _cfg_detail_on()

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(404, text="not found")
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai",
            keywords=("测试",),
            max_pages=1,
            max_jobs=10,
        )

    # Crawl-level status is OK — a 404 on one detail must not escalate to ERROR.
    assert result.status is SourceStatus.OK
    # Listing-only data preserved; freshness reflects the 404.
    assert len(result.jobs) == 1
    j = result.jobs[0]
    assert j.company is None
    assert j.url_status is UrlStatus.GONE
    assert j.url_last_checked_at is not None
    assert j.data_quality == 1.0   # ADR 0003: gone does NOT lower data_quality


@respx.mock
@pytest.mark.asyncio
async def test_crawl_with_detail_block_converts_to_partial_harvest(tmp_path: Path) -> None:
    """A 200 detail response containing a content_block_marker must:
    - convert the run to PartialHarvest (reason starts 'partial:'),
    - NOT write a blob for the blocked URL,
    - NOT write a successful url_cache row for the blocked URL.
    """
    cfg = _cfg_detail_on_with_block_marker()

    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=_LISTING_HTML)
    )
    respx.get("https://testerhome.com/topics/42").mock(
        return_value=httpx.Response(200, text=_FIX_BLOCKED.read_text(encoding="utf-8"))
    )

    async with httpx.AsyncClient() as ac:
        src = _make_source(cfg, tmp_path, ac)
        result = await src.crawl(
            region="Shanghai",
            keywords=("测试",),
            max_pages=2,
            max_jobs=10,
        )

    assert result.status == SourceStatus.OK  # partial == status OK + 'partial:' reason
    assert result.reason.startswith("partial:")
    assert "detail block" in result.reason
    # Listing data preserved.
    assert len(result.jobs) == 1
    assert result.jobs[0].company is None
    # No raw blob was written for /topics/42 (detail was blocked).
    raw_dir = tmp_path / "raw" / "testerhome"
    detail_blob_count = sum(1 for _ in raw_dir.rglob("*.html.gz")) if raw_dir.exists() else 0
    # Only the listing page should have a blob.
    assert detail_blob_count == 1
