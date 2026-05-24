"""build_view_context — pure helper that turns a Run + jobs into a template dict."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Run, Salary, SalaryPeriod
from jma.report.view import build_view_context


def _job(
    *,
    title="AI Agent Engineer",
    company: str | None = "ACME",
    posted_at: datetime | None = None,
    salary_raw="20-40K",
    parsed=True,
    blob="raw/bing/20260524/abc1234567890def.json.gz",
) -> Job:
    return Job(
        id=job_id(
            source="bing:zhipin.com", internal_id="1", title=title, company=company, city=None
        ),
        canonical_id=canonical_id(title=title, company=company, city=None),
        source="bing:zhipin.com",
        source_internal_id="1",
        title=title,
        title_raw=title,
        company=company,
        location=Location(country="CN"),
        salary=Salary(
            min=20000 if parsed else None,
            max=40000 if parsed else None,
            currency="CNY" if parsed else None,
            period=SalaryPeriod.MONTHLY if parsed else SalaryPeriod.UNKNOWN,
            raw=salary_raw,
            parsed=parsed,
        ),
        experience=Experience(),
        posted_at=posted_at,
        fetched_at=datetime(2026, 5, 24, 0, 0, 0, tzinfo=UTC),
        url=f"https://zhipin.com/job/{title}",
        raw_payload_ref=blob,
        data_quality=0.4,
        description_text="snippet",
    )


def _run() -> Run:
    return Run(
        id="deadbeef" * 4,
        region="Hangzhou",
        keywords=("AI agent",),
        started_at=datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 24, 10, 5, 0, tzinfo=UTC),
    )


def test_context_carries_run_metadata_and_count():
    jobs = [_job(title="A"), _job(title="B")]
    ctx = build_view_context(_run(), jobs, Path("/tmp/jma-test"))

    assert ctx["run"]["id"].startswith("deadbeef")
    assert ctx["run"]["region"] == "Hangzhou"
    assert ctx["run"]["keywords"] == ("AI agent",)
    assert ctx["count"] == 2
    assert ctx["data_root_abs"] == "/tmp/jma-test"


def test_context_preserves_input_job_order():
    """SQL-side ordering is exercised in test_jobs_for_run; this only checks
    that build_view_context does not re-sort."""
    jobs = [_job(title="C"), _job(title="A"), _job(title="B")]
    ctx = build_view_context(_run(), jobs, Path("/tmp"))
    titles = [r["title"] for r in ctx["rows"]]
    assert titles == ["C", "A", "B"]


def test_context_row_shape():
    j = _job()
    ctx = build_view_context(_run(), [j], Path("/tmp"))
    row = ctx["rows"][0]
    assert row["title"] == "AI Agent Engineer"
    assert row["company"] == "ACME"
    assert row["city"] is None  # we render None → em-dash in template, not here
    assert row["salary_raw"] == "20-40K"
    assert row["posted_at"] is None
    assert row["source"] == "bing:zhipin.com"
    assert row["url"].startswith("https://")
    assert row["raw_payload_ref"].endswith(".json.gz")
    assert row["dq"] == 0.4


def test_context_handles_none_company():
    j = _job(company=None)
    ctx = build_view_context(_run(), [j], Path("/tmp"))
    assert ctx["rows"][0]["company"] is None
