from pathlib import Path

import httpx
import pytest

from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"


@pytest.mark.live
@pytest.mark.asyncio
async def test_testerhome_live_smoke(tmp_path: Path) -> None:
    cfg = load_source_config(CFG_PATH)
    async with httpx.AsyncClient(
        headers={
            "User-Agent": "jma-live-smoke/0.1 (+https://github.com/snowshine0216/job-market-agent)"
        },
        timeout=30.0,
    ) as ac:
        http = AsyncHttpClient(ac, rate=cfg.rate)
        src = TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path)
        result = await src.crawl(region="", keywords=("",), max_pages=1, max_jobs=50)

    assert result.status.value == "ok", f"unexpected status: {result.status} ({result.reason})"
    assert len(result.jobs) >= 1, "expected at least one job from live TesterHome listing page 1"
