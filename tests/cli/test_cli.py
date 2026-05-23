from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from jma.cli import app

REPO = Path(__file__).resolve().parents[2]
FIX_OK = (REPO / "tests/fixtures/sources/testerhome/listing_ok.html").read_text(encoding="utf-8")
FIX_EMPTY = (REPO / "tests/fixtures/sources/testerhome/listing_empty.html").read_text(
    encoding="utf-8"
)


@respx.mock
def test_crawl_success_exit_zero(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
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
            "3",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0, result.stdout
    assert "run_id" in result.stdout
    assert "testerhome" in result.stdout
    assert "ok" in result.stdout


@respx.mock
def test_crawl_partial_harvest_still_exit_zero(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(429, headers={"retry-after": "30"}, text="")
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["crawl", "--region", "", "--keywords", "", "--max-pages", "3", "--max-jobs", "100"],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert "partial" in result.stdout


@respx.mock
def test_crawl_all_blocked_exit_two(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
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
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 2
    assert "blocked" in result.stdout.lower() or "HTTP 403" in result.stdout


@respx.mock
def test_crawl_empty_listing_exit_two(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
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
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 2


@respx.mock
def test_crawl_multiple_keywords_are_ored(tmp_path: Path) -> None:
    respx.get("https://testerhome.com/jobs?page=1").mock(
        return_value=httpx.Response(200, text=FIX_OK)
    )
    respx.get("https://testerhome.com/jobs?page=2").mock(
        return_value=httpx.Response(200, text=FIX_EMPTY)
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
            "3",
            "--max-jobs",
            "100",
        ],
        env={"JMA_DATA_ROOT": str(tmp_path)},
    )
    assert result.exit_code == 0
    # All three fixture items should be retained: 2 contain "AI agent", 1 contains "Senior".
    assert "jobs=3" in result.stdout
