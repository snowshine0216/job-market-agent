"""Live SerpAPI smoke. Opt in with: uv run pytest -m live tests/live/test_bing_live.py

Burns ~1 SerpAPI quota credit per run. Default pytest config (-m 'not live')
skips this entire file.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from jma.domain.models import SourceStatus
from jma.sources.base import load_source_config
from jma.sources.bing import BingAggregatorSource
from jma.sources.http import AsyncHttpClient

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.live
@pytest.mark.asyncio
async def test_bing_live_one_page_hangzhou_ai_agent(tmp_path):
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        pytest.skip("SERPAPI_KEY not set; skipping live smoke")

    cfg = load_source_config(REPO / "config/sources/bing.yaml")
    async with httpx.AsyncClient(timeout=30.0) as ac:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        src = BingAggregatorSource(
            cfg=cfg,
            http=http,
            data_root=tmp_path,
            api_key=api_key,
        )
        result = await src.crawl(
            region="Hangzhou", keywords=("AI agent",), max_pages=1, max_jobs=200
        )

    assert result.status is SourceStatus.OK
    assert len(result.jobs) >= 1, "SerpAPI returned no organic_results"

    hosts = {j.source.removeprefix("bing:") for j in result.jobs}
    # Sanity: at least one host from target_sites is present (validates the
    # site: operator survives the SerpAPI bridge).
    assert hosts.intersection(set(cfg.target_sites)), f"no target host in {hosts}"

    # Snippet-richness tripwire (spec §6 live test description):
    # ≥1 parseable salary, ≥1 posted_at, ≥1 experience.min_years
    assert any(j.salary.parsed for j in result.jobs), "no row has a parseable salary"
    assert any(j.posted_at is not None for j in result.jobs), "no row has posted_at"
    assert any(j.experience.min_years is not None for j in result.jobs), (
        "no row has experience.min_years — snippets may have degraded to title-only"
    )
