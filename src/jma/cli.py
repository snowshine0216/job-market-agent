"""`jma` Typer entry-point (spec §8)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
import typer

from jma.domain.models import SourceResult, SourceStatus, UrlStatus
from jma.pipeline.crawl import run as pipeline_run
from jma.sources.base import JobSource, load_source_config
from jma.sources.http import AsyncHttpClient

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def _callback() -> None:
    """jma — job-market-agent CLI."""


_CFG_DIR = Path(__file__).resolve().parents[2] / "config" / "sources"


def _data_root() -> Path:
    env = os.environ.get("JMA_DATA_ROOT")
    if env:
        return Path(env)
    return Path.cwd() / "data"


def _check_required_env_for_sources(source_names: list[str]) -> None:
    """Raise typer.Exit(1) with a clear message if any selected source's
    api_key_env is unset. Runs after Typer arg parsing, before the DB opens
    (spec §2 row 9). Pure on env state."""
    for name in source_names:
        try:
            cfg = load_source_config(_CFG_DIR / f"{name}.yaml")
        except FileNotFoundError:
            continue  # _factory_for will raise a clearer error later
        env_name = getattr(cfg, "api_key_env", None)
        if env_name and not os.environ.get(env_name):
            typer.echo(f"missing env var {env_name} (required by source {name!r})", err=True)
            raise typer.Exit(code=1)


def _factory_for(source_name: str, data_root: Path):
    cfg = load_source_config(_CFG_DIR / f"{source_name}.yaml")
    if source_name == "bing":
        # Lazy import so `jma view` works even if jma.sources.bing has a syntax-time issue.
        from jma.sources.bing import BingAggregatorSource

        def _make(ac: httpx.AsyncClient, on_fetch, cache_get) -> JobSource:
            http = AsyncHttpClient(ac, rate=cfg.rate)
            return BingAggregatorSource(
                cfg=cfg,
                http=http,
                data_root=data_root,
                api_key=os.environ[cfg.api_key_env],
                on_fetch=on_fetch,
                cache_get=cache_get,
            )

        return _make
    raise KeyError(f"unknown source: {source_name!r}")


def _summary_lines(
    run_id: str, region: str, keywords: tuple[str, ...], results: list[SourceResult], db_path: Path
) -> list[str]:
    lines = [
        f"run_id        : {run_id}",
        f"region        : {region or '(empty)'}",
        f"keywords      : {', '.join(keywords) if keywords else '(empty)'}",
        "sources:",
    ]
    total_obs = 0
    for r in results:
        n = len(r.jobs)
        total_obs += n
        if r.status is SourceStatus.OK:
            line = f"  {r.source:<11}: ok    pages={r.pages_fetched}  jobs={n}"
            if any(j.url_last_checked_at is not None for j in r.jobs):
                gone = sum(1 for j in r.jobs if j.url_status is UrlStatus.GONE)
                line += f"   gone_urls={gone}"
            line += f"   elapsed={r.elapsed_ms / 1000:.1f}s"
            if r.reason.startswith("partial:"):
                line += f"  {r.reason}"
            lines.append(line)
        else:
            lines.append(
                f'  {r.source:<11}: {r.status.value}  reason="{r.reason}"  pages={r.pages_fetched}  jobs={n}'
            )
    lines.append(f"written       : {total_obs} observations to {db_path}")
    return lines


def _exit_code(results: list[SourceResult]) -> int:
    for r in results:
        if r.status is SourceStatus.OK and len(r.jobs) >= 1:
            return 0
    return 2


@app.command()
def crawl(
    region: str = typer.Option(
        ..., "--region", help="Region (e.g. Hangzhou). Empty disables region filter."
    ),
    keywords: list[str] = typer.Option(..., "--keywords", help="Repeatable keyword phrase."),
    source: list[str] = typer.Option(["bing"], "--source", help="Source name (repeatable)."),
    max_pages: int = typer.Option(5, "--max-pages"),
    max_jobs: int = typer.Option(300, "--max-jobs"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Fail fast on missing env vars required by selected sources (spec §2 row 9).
    _check_required_env_for_sources(source)
    keywords_t = tuple(keywords)
    data_root = _data_root()  # resolve once; used in factory, pipeline, and summary
    db_path = data_root / "jobs.db"

    async def _run_all() -> tuple[str, list[SourceResult]]:
        all_results: list[SourceResult] = []
        run_id_final: str | None = None
        for s_name in source:
            run_id, results = await pipeline_run(
                region=region,
                keywords=keywords_t,
                source_factory=_factory_for(s_name, data_root),
                db_path=db_path,
                data_root=data_root,
                max_pages=max_pages,
                max_jobs=max_jobs,
                use_cache=not no_cache,
            )
            # Phase 2 TODO: when multi-source is enabled, create one shared run_id before the source loop (spec §2 row 6).
            run_id_final = run_id  # Phase 1: one source, single Run is fine
            all_results.extend(results)
        assert run_id_final is not None
        return run_id_final, all_results

    try:
        run_id, results = asyncio.run(_run_all())
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for line in _summary_lines(run_id, region, keywords_t, results, db_path):
        typer.echo(line)

    raise typer.Exit(code=_exit_code(results))


@app.command()
def view(
    run: str | None = typer.Option(
        None, "--run", help="Render this specific run id (full hex). Defaults to latest finished."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Output path. Defaults to {data_root}/view.html."
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the rendered file in the default browser after writing.",
    ),
) -> None:
    """Render the latest finished run (or --run <id>) to a static HTML page."""
    import shutil
    import subprocess
    import sys

    import jinja2

    from jma.report.view import build_view_context
    from jma.storage.db import get_run, jobs_for_run, latest_finished_run, open_db

    data_root = _data_root()
    db_path = data_root / "jobs.db"
    out_path = out if out is not None else (data_root / "view.html")

    async def _go() -> tuple[str, int]:
        ctx_db = await open_db(db_path)
        async with ctx_db as conn:
            if run is None:
                run_row = await latest_finished_run(conn)
                if run_row is None:
                    typer.echo(
                        f"no finished runs in {db_path}; run 'jma crawl ...' first", err=True
                    )
                    raise typer.Exit(code=2)
            else:
                run_row = await get_run(conn, run)
                if run_row is None:
                    typer.echo(f"no run {run} in {db_path}", err=True)
                    raise typer.Exit(code=2)
                if run_row.finished_at is None:
                    typer.echo(f"run {run} is not finished; nothing to render", err=True)
                    raise typer.Exit(code=2)
            jobs = await jobs_for_run(conn, run_row.id)

        context = build_view_context(run_row, jobs, data_root.resolve())
        template_dir = Path(__file__).resolve().parent / "report" / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml", "j2"]),
        )
        html = env.get_template("view.html.j2").render(**context)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        return run_row.id, len(jobs)

    rendered_run_id, n = asyncio.run(_go())
    typer.echo(f"wrote {out_path} (run {rendered_run_id[:8]}, {n} observations)")

    if open_browser:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if shutil.which(opener):
            subprocess.run([opener, str(out_path)], check=False)
