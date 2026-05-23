from datetime import UTC, datetime
from pathlib import Path

from jma.cli import _summary_lines
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
    UrlStatus,
)


def _job(*, status: UrlStatus, checked: bool, suffix: str = "") -> Job:
    return Job(
        id=job_id(source="testerhome", internal_id=f"{status.value}{suffix}",
                  title="t", company=None, city=None),
        canonical_id=canonical_id(title=f"t{suffix}", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime.now(UTC),
        url=f"https://x/{status.value}{suffix}",
        raw_payload_ref="x.gz",
        url_status=status,
        url_last_checked_at=datetime.now(UTC) if checked else None,
    )


def test_summary_includes_gone_count_when_detail_ran() -> None:
    jobs = (
        _job(status=UrlStatus.LIVE, checked=True, suffix="a"),
        _job(status=UrlStatus.GONE, checked=True, suffix="b"),
        _job(status=UrlStatus.GONE, checked=True, suffix="c"),
    )
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls=2" in src_line


def test_summary_includes_gone_zero_when_detail_ran_and_all_live() -> None:
    jobs = (_job(status=UrlStatus.LIVE, checked=True, suffix="a"),)
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls=0" in src_line


def test_summary_omits_gone_segment_for_listing_only_crawl() -> None:
    """No Job has url_last_checked_at -> the source didn't do detail fetches.
    Don't print gone_urls=0 (misleading); omit the segment entirely."""
    jobs = (
        _job(status=UrlStatus.UNKNOWN, checked=False, suffix="a"),
        _job(status=UrlStatus.UNKNOWN, checked=False, suffix="b"),
    )
    result = SourceResult(
        source="testerhome", status=SourceStatus.OK, jobs=jobs,
        pages_fetched=1, elapsed_ms=1234,
    )
    lines = _summary_lines(
        run_id="rid", region="Hangzhou", keywords=("测试",),
        results=[result], db_path=Path("/tmp/x.db"),
    )
    src_line = next(l for l in lines if l.startswith("  testerhome"))
    assert "gone_urls" not in src_line
