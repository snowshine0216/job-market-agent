from pathlib import Path

import httpx
import pytest
import respx

from jma.pipeline.crawl import run
from jma.sources.base import load_source_config
from jma.sources.http import AsyncHttpClient
from jma.sources.testerhome import TesterHomeSource

REPO = Path(__file__).resolve().parents[2]
CFG_PATH = REPO / "config/sources/testerhome.yaml"
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(encoding="utf-8")


def _factory(tmp_path: Path):
    async def _no_sleep(_s: float) -> None: return None
    cfg = load_source_config(CFG_PATH)

    def _make(ac: httpx.AsyncClient, on_fetch):
        http = AsyncHttpClient(ac, rate=cfg.rate, sleep=_no_sleep)
        return TesterHomeSource(cfg=cfg, http=http, data_root=tmp_path,
                                sleep=_no_sleep, on_fetch=on_fetch)
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
