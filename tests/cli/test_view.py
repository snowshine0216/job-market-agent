"""Typer CliRunner tests for `jma view`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from jma.cli import app
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary
from jma.storage.db import finish_run, insert_jobs, open_db, start_run


def _seed_db_with_one_finished_run(db_path: Path) -> str:
    async def _go() -> str:
        ctx = await open_db(db_path)
        async with ctx as conn:
            run_id = await start_run(conn, region="Hangzhou", keywords=("AI agent",))
            j = Job(
                id=job_id(
                    source="bing:zhipin.com",
                    internal_id="1",
                    title="AI Agent",
                    company="ACME",
                    city=None,
                ),
                canonical_id=canonical_id(title="AI Agent", company="ACME", city=None),
                source="bing:zhipin.com",
                source_internal_id="1",
                title="AI Agent",
                title_raw="AI Agent",
                company="ACME",
                location=Location(country="CN"),
                salary=Salary(parsed=False, raw=""),
                experience=Experience(),
                fetched_at=datetime(2026, 5, 24, tzinfo=UTC),
                url="https://www.zhipin.com/job_detail/1.html",
                raw_payload_ref="raw/bing/20260524/abc.json.gz",
                data_quality=0.4,
            )
            await insert_jobs(conn, run_id, [j])
            await finish_run(conn, run_id=run_id, source_results=[])
        return run_id

    return asyncio.run(_go())


def test_view_empty_db_exits_nonzero_with_clear_message(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["view"])
    assert result.exit_code != 0
    assert "no finished runs" in result.output


def test_view_latest_finished_run_writes_default_file(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    run_id = _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    runner = CliRunner()
    result = runner.invoke(app, ["view"])
    assert result.exit_code == 0, result.output
    out_path = tmp_path / "view.html"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert run_id[:8] in content
    assert "n=1" in content
    assert "wrote" in result.output and "view.html" in result.output


def test_view_custom_out_path(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    out = tmp_path / "elsewhere" / "x.html"
    runner = CliRunner()
    result = runner.invoke(app, ["view", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()


def test_view_unknown_run_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))
    _seed_db_with_one_finished_run(tmp_path / "jobs.db")

    runner = CliRunner()
    result = runner.invoke(app, ["view", "--run", "deadbeef" * 4])
    assert result.exit_code != 0
    assert "no run" in result.output


def test_view_unfinished_run_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("JMA_DATA_ROOT", str(tmp_path))

    async def _go() -> str:
        ctx = await open_db(tmp_path / "jobs.db")
        async with ctx as conn:
            return await start_run(conn, region="r", keywords=("k",))

    unfinished_id = asyncio.run(_go())

    runner = CliRunner()
    result = runner.invoke(app, ["view", "--run", unfinished_id])
    assert result.exit_code != 0
    assert "not finished" in result.output
