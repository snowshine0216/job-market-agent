import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from jma.cli import app

REPO = Path(__file__).resolve().parents[2]

# Minimal SerpAPI JSON payload with one on-target result for Hangzhou AI agent.
_SERPAPI_ONE_JOB = json.dumps({
    "organic_results": [
        {
            "title": "AI Agent Engineer | BOSS直聘",
            "link": "https://www.zhipin.com/job_detail/123.html",
            "snippet": "Hangzhou 20-40K 3-5年",
        }
    ]
})

_SERPAPI_EMPTY = json.dumps({"organic_results": []})


@respx.mock
def test_crawl_success_exit_zero(tmp_path: Path) -> None:
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=_SERPAPI_ONE_JOB)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "crawl",
            "--region",
            "Hangzhou",
            "--keywords",
            "AI agent",
            "--max-pages",
            "1",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path), "SERPAPI_KEY": "testkey"},
    )
    assert result.exit_code == 0, result.stdout
    assert "run_id" in result.stdout
    assert "bing" in result.stdout
    assert "ok" in result.stdout


@respx.mock
def test_crawl_all_blocked_exit_two(tmp_path: Path) -> None:
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(403, text="forbid")
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "crawl",
            "--region",
            "Hangzhou",
            "--keywords",
            "AI",
            "--max-pages",
            "1",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path), "SERPAPI_KEY": "testkey"},
    )
    assert result.exit_code == 2


@respx.mock
def test_crawl_empty_listing_exit_two(tmp_path: Path) -> None:
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=_SERPAPI_EMPTY)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "crawl",
            "--region",
            "Hangzhou",
            "--keywords",
            "AI",
            "--max-pages",
            "1",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path), "SERPAPI_KEY": "testkey"},
    )
    assert result.exit_code == 2


@respx.mock
def test_crawl_multiple_keywords_are_ored(tmp_path: Path) -> None:
    payload = json.dumps({
        "organic_results": [
            {
                "title": "AI Agent Engineer | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/1.html",
                "snippet": "Hangzhou",
            },
            {
                "title": "Senior Engineer | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/2.html",
                "snippet": "Hangzhou",
            },
            {
                "title": "Senior AI Agent Platform Engineer | BOSS直聘",
                "link": "https://www.zhipin.com/job_detail/3.html",
                "snippet": "Hangzhou",
            },
        ]
    })
    respx.get("https://serpapi.com/search").mock(
        return_value=httpx.Response(200, text=payload)
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "crawl",
            "--region",
            "",
            "--keywords",
            "AI agent",
            "--keywords",
            "Senior",
            "--max-pages",
            "1",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path), "SERPAPI_KEY": "testkey"},
    )
    assert result.exit_code == 0
    assert "jobs=3" in result.stdout
