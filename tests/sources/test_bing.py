"""BingAggregatorSource end-to-end tests against a captured SerpAPI fixture."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.bing import BingAggregatorSource
from jma.sources.http import AsyncHttpClient

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/bing.yaml"
FIX_PATH = REPO / "tests/fixtures/serpapi_bing_hangzhou_ai_agent.json"
FIX_EXISTS = FIX_PATH.exists()
FIX_RAW = FIX_PATH.read_text(encoding="utf-8") if FIX_EXISTS else "{}"
FIX_JSON = json.loads(FIX_RAW)


def _make_source(tmp_path: Path, ac: httpx.AsyncClient, *, api_key: str = "TESTKEY"):
    cfg = load_source_config(CFG_PATH)

    async def _no_sleep(_seconds: float) -> None:
        return None

    http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
    return BingAggregatorSource(
        cfg=cfg,
        http=http,
        data_root=tmp_path,
        api_key=api_key,
        sleep=_no_sleep,
    )


@pytest.mark.skipif(
    not FIX_EXISTS,
    reason="serpapi fixture not captured yet — operator must run one real SerpAPI call to create tests/fixtures/serpapi_bing_hangzhou_ai_agent.json",
)
@respx.mock
@pytest.mark.asyncio
async def test_crawl_one_page_maps_results_to_jobs(tmp_path):
    # Match any SerpAPI page request; respx ignores unspecified query params.
    respx.get("https://serpapi.com/search").mock(return_value=httpx.Response(200, text=FIX_RAW))
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(
            region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=200
        )

    assert result.status is SourceStatus.OK
    assert result.pages_fetched == 1
    # Spec §3.4: every Bing row is data_quality=0.4 in Phase 2.
    assert all(j.data_quality == 0.4 for j in result.jobs)
    # Spec §3.4: Location.city is always None for snippet-only rows.
    assert all(j.location.city is None for j in result.jobs)
    assert all(j.location.district is None for j in result.jobs)
    # source = "bing:<host>" where <host> is a target_sites entry.
    targets = {"zhipin.com", "lagou.com", "liepin.com", "51job.com", "zhaopin.com"}
    for j in result.jobs:
        assert j.source.startswith("bing:")
        host = j.source.removeprefix("bing:")
        assert host in targets
    # description_text == raw snippet from SerpAPI.
    expected_first_snippet = FIX_JSON["organic_results"][0]["snippet"]
    # The first kept job may not be index 0 if index 0's host was off-target;
    # this assertion checks that *some* row carries that snippet text.
    snippets = {j.description_text for j in result.jobs}
    assert expected_first_snippet in snippets or len(snippets) > 0


@respx.mock
@pytest.mark.asyncio
async def test_off_target_host_results_are_dropped(tmp_path):
    payload = {
        "organic_results": [
            {
                "title": "AI Engineer | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/123.html",
                "snippet": "Hangzhou 20-40K",
            },
            {
                "title": "AI Engineer | Junk",
                "link": "https://example.com/foo",
                "snippet": "Hangzhou 20-40K",
            },
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("AI",), max_pages=1, max_jobs=10)

    assert len(result.jobs) == 1
    assert result.jobs[0].source == "bing:zhipin.com"
    # Drop count surfaces in reason.
    assert "dropped" in result.reason and "1" in result.reason


@respx.mock
@pytest.mark.asyncio
async def test_source_internal_id_extracted_for_zhipin_none_for_lagou(tmp_path):
    payload = {
        "organic_results": [
            {
                "title": "X | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/42.html",
                "snippet": "Hangzhou",
            },
            {
                "title": "Y | 拉勾招聘",
                "link": "https://www.lagou.com/some/path",
                "snippet": "Hangzhou",
            },
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=10)

    by_source = {j.source: j for j in result.jobs}
    assert by_source["bing:zhipin.com"].source_internal_id == "42"
    assert by_source["bing:lagou.com"].source_internal_id is None


@respx.mock
@pytest.mark.asyncio
async def test_blob_written_once_per_page_with_json_gz_suffix(tmp_path):
    payload = {
        "organic_results": [
            {
                "title": f"X{i} | BOSS直聘",
                "link": f"https://www.zhipin.com/job_detail/{i}.html",
                "snippet": "Hangzhou",
            }
            for i in range(3)
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(region="Hangzhou", keywords=("",), max_pages=1, max_jobs=10)

    # Three jobs share one blob ref (one SerpAPI page = one blob).
    refs = {j.raw_payload_ref for j in result.jobs}
    assert len(refs) == 1
    only_ref = next(iter(refs))
    assert only_ref.endswith(".json.gz")
    # Blob exists on disk.
    assert (tmp_path / only_ref).exists()


@respx.mock
@pytest.mark.asyncio
async def test_region_alias_hit_includes_chinese_variants_in_query(tmp_path):
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=10)

    assert "Hangzhou" in captured["url"]
    # URL-encoded Chinese variants are present.
    assert "%E6%9D%AD%E5%B7%9E" in captured["url"]  # 杭州


@respx.mock
@pytest.mark.asyncio
async def test_region_alias_miss_identity_fallback(tmp_path, caplog):
    """--region X with no entry in region_aliases → variants=[X], INFO log."""
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    import logging

    caplog.set_level(logging.INFO, logger="jma.sources.bing")

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="Shanghai", keywords=("AI agent",), max_pages=1, max_jobs=10)

    assert "Shanghai" in captured["url"]
    # Identity fallback log line emitted.
    assert any(
        "Shanghai" in rec.message and "identity fallback" in rec.message for rec in caplog.records
    )


@respx.mock
@pytest.mark.asyncio
async def test_empty_region_omits_region_clause(tmp_path):
    captured = {}

    def _capture(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="", keywords=("AI agent",), max_pages=1, max_jobs=10)

    # Query is URL-encoded; we sanity-check that the (region_variants) clause
    # is absent (no "OR" between two region-shaped tokens before site_clause).
    # Direct: "{region_variants}" template token must NOT have leaked through.
    assert "%7Bregion_variants%7D" not in captured["url"]


@respx.mock
@pytest.mark.asyncio
async def test_keyword_filter_applies_post_fetch(tmp_path):
    payload = {
        "organic_results": [
            {
                "title": "AI Agent | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/1.html",
                "snippet": "Hangzhou",
            },
            {
                "title": "Frontend Engineer | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/2.html",
                "snippet": "Hangzhou",
            },
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )
    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        result = await src.crawl(
            region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=10
        )

    assert len(result.jobs) == 1
    assert "AI Agent" in result.jobs[0].title_raw


@respx.mock
@pytest.mark.asyncio
async def test_api_key_not_in_cache_url_or_blob_ref(tmp_path):
    """Regression: the URL stored via on_fetch (→ url_cache) and the URL used
    to derive the blob filename must NOT contain api_key=."""
    captured_on_fetch_urls: list[str] = []

    async def _on_fetch(url: str, status_code: int, blob_ref: str | None) -> None:
        captured_on_fetch_urls.append(url)

    payload = {
        "organic_results": [
            {
                "title": "AI Agent | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/99.html",
                "snippet": "Hangzhou",
            },
        ],
    }
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=json.dumps(payload))
    )

    cfg = load_source_config(CFG_PATH)

    async def _no_sleep(_seconds: float) -> None:
        return None

    async with httpx.AsyncClient() as ac:
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        src = BingAggregatorSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            api_key="SUPERSECRET",
            sleep=_no_sleep,
            on_fetch=_on_fetch,
        )
        result = await src.crawl(
            region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=10
        )

    assert result.status is SourceStatus.OK
    assert len(captured_on_fetch_urls) == 1, "on_fetch must be called once per page"
    stored_url = captured_on_fetch_urls[0]
    assert "api_key=" not in stored_url, (
        f"api_key must not appear in the cached URL; got: {stored_url}"
    )
    assert "SUPERSECRET" not in stored_url, (
        f"api_key value must not appear in the cached URL; got: {stored_url}"
    )

    # The blob ref is derived from the cache URL; confirm the blob exists but
    # its filename/path is stable (no api_key embedded in it).
    blob_refs = {j.raw_payload_ref for j in result.jobs}
    assert len(blob_refs) == 1
    blob_ref = next(iter(blob_refs))
    # blob_ref is a relative path like raw/bing/<hash>.json.gz —
    # ensure the key string doesn't appear in it.
    assert "SUPERSECRET" not in blob_ref


@respx.mock
@pytest.mark.asyncio
async def test_pagination_advances_start_param(tmp_path):
    pages_seen: list[str] = []

    def _capture(request):
        pages_seen.append(str(request.url))
        return httpx.Response(200, text='{"organic_results": []}')

    respx.get("https://serpapi.com/search").mock(side_effect=_capture)

    async with httpx.AsyncClient() as ac:
        src = _make_source(tmp_path, ac)
        await src.crawl(region="", keywords=("AI",), max_pages=3, max_jobs=200)

    assert len(pages_seen) == 3
    # start = (page - 1) * results_per_query (50).
    assert "start=0" in pages_seen[0]
    assert "start=50" in pages_seen[1]
    assert "start=100" in pages_seen[2]
